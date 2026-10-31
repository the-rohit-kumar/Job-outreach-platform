"""Self-check: a second pass that rejects generic, repetitive, over-claimed or
hook-less drafts. Two failures -> "needs manual touch" list.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Draft, Lead, Profile
from . import llm

logger = logging.getLogger("outreachhub.selfcheck")

GENERIC_PHRASES = [
    "i am excited to apply",
    "i hope this message finds you well",
    "i am writing to express my interest",
    "i believe i would be a great fit",
    "i came across your company on",
    "i am confident that my skills",
    "i would welcome the opportunity",
    "thank you for your time and consideration",
]

CLAIM_PATTERNS = [
    re.compile(r"\b\d{1,3}%"),
    re.compile(r"\b(increased|boosted|improved|reduced|grew|saved|doubled)\b[^.]{0,40}\b\d", re.I),
    re.compile(r"\b(award-winning|top-rated|world-class|cutting-edge|best-in-class|industry-leading)\b", re.I),
]


@dataclass
class CheckResult:
    ok: bool
    checks: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w]) if text else 0


def _tone(profile: Profile | None) -> dict:
    return (profile.tone if profile else {}) or {}


def check_draft(
    db: Session,
    draft: Draft,
    lead: Lead | None = None,
    profile: Profile | None = None,
    *,
    recent_bodies: list[str] | None = None,
) -> CheckResult:
    profile = profile or db.get(Profile, 1)
    lead = lead or db.get(Lead, draft.lead_id)
    tone = _tone(profile)
    text = f"{draft.subject}\n{draft.body}".strip()
    low = text.lower()
    reasons: list[str] = []
    checks: dict = {}

    # 1) length
    if draft.variant == "email":
        limit = int(tone.get("max_email_words", 120))
        count = word_count(draft.body)
        checks["words"] = count
        if count > limit:
            reasons.append(f"email is {count} words (limit {limit})")
    else:
        limit = int(tone.get("max_linkedin_note_chars", 300))
        checks["chars"] = len(draft.body)
        if len(draft.body) > limit:
            reasons.append(f"{len(draft.body)} chars (limit {limit})")

    # 2) do-not-mention list
    forbidden = [t for t in (profile.do_not_mention or []) if t]
    hits = [t for t in forbidden if re.search(rf"\b{re.escape(t.lower())}\b", low)]
    checks["do_not_mention_hits"] = hits
    if hits:
        reasons.append(f"mentions forbidden topic: {', '.join(hits)}")
    if re.search(r"\bsap\b", low):
        reasons.append("mentions SAP")
    if re.search(r"\bclient name", low) or re.search(r"\binternal (ticket|jira|tool|system)s?\b", low):
        reasons.append("sounds like it references client/internal details")

    # 3) unsupported claims
    claims = [p.pattern for p in CLAIM_PATTERNS if p.search(text)]
    checks["claim_patterns"] = claims
    if claims:
        reasons.append("contains unverifiable metric/marketing claims")

    # 4) generic phrasing
    generic = [p for p in GENERIC_PHRASES if p in low]
    checks["generic_phrases"] = generic
    if generic:
        reasons.append(f"generic phrasing: '{generic[0]}'")

    # 5) repetition against recent drafts
    if recent_bodies is None:
        recent_bodies = _recent_bodies(db, exclude_id=draft.id)
    similarity, twin = _max_similarity(draft.body, recent_bodies)
    checks["max_similarity"] = round(similarity, 3)
    if similarity >= 0.82:
        reasons.append(f"reuses phrasing seen in recent drafts ({similarity:.0%} similar)")

    # 6) company-specific hook
    hook_ok, hook_reason = _hook_check(draft, lead, low)
    checks["hook_ok"] = hook_ok
    if not hook_ok:
        reasons.append(hook_reason)

    # 7) opt-out line
    if tone.get("include_opt_out_line", True) and not _has_opt_out(low):
        checks["opt_out"] = False
        if draft.variant == "email":
            reasons.append("missing the polite opt-out line")
    else:
        checks["opt_out"] = True

    # 8) ask present
    ask_ok = any(
        k in low
        for k in ("few hours a week", "part-time", "contract", "trial task", "availability")
    )
    checks["ask_ok"] = ask_ok
    if not ask_ok:
        reasons.append("missing the clear ask (hours/availability/trial task)")

    return CheckResult(ok=not reasons, checks=checks, reasons=reasons)


def _has_opt_out(low: str) -> bool:
    return any(
        k in low
        for k in (
            "not a fit",
            "no worries",
            "feel free to ignore",
            "won't follow up",
            "no need to reply",
            "just say no",
            "not looking",
        )
    )


def _hook_check(draft: Draft, lead: Lead | None, low: str) -> tuple[bool, str]:
    if lead is None:
        return True, ""
    company = (lead.company or "").strip().lower()
    hook = (lead.hook or "").strip().lower()
    company_ok = bool(company) and len(company) > 2 and company in low
    hook_ok = False
    if hook:
        probe = re.sub(r"[^a-z0-9 ]", "", hook)[:60].strip()
        words = [w for w in probe.split() if len(w) > 3][:8]
        if words:
            hook_ok = sum(1 for w in words if w in low) >= max(2, len(words) // 3)
    if company_ok or hook_ok:
        return True, ""
    if not hook and not company:
        return False, "no company/product detail available to reference (skip the lead)"
    return False, "lacks a company-specific hook (name or product reference missing)"


def _recent_bodies(db: Session, exclude_id: int | None = None, limit: int = 50) -> list[str]:
    q = db.query(Draft).filter(Draft.created_at >= datetime.now(timezone.utc) - timedelta(days=14))
    if exclude_id:
        q = q.filter(Draft.id != exclude_id)
    rows = q.order_by(Draft.id.desc()).limit(limit).all()
    return [r.body for r in rows if r.body]


def _max_similarity(body: str, others: list[str]) -> tuple[float, str]:
    if not body or not others:
        return 0.0, ""
    best = 0.0
    twin = ""
    mine = _shingles(body)
    if not mine:
        return 0.0, ""
    for other in others:
        theirs = _shingles(other)
        if not theirs:
            continue
        score = len(mine & theirs) / len(mine | theirs)
        if score > best:
            best, twin = score, other
    return best, twin


def _shingles(text: str, n: int = 4) -> set[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def run_self_check(db: Session) -> dict:
    """Check pending drafts; regenerate once on failure; twice -> needs_manual."""
    from . import drafting

    profile = db.get(Profile, 1)
    pending = db.query(Draft).filter(Draft.status == "pending").all()
    passed = failed = regenerated = manual = 0

    for draft in pending:
        lead = db.get(Lead, draft.lead_id)
        result = check_draft(db, draft, lead, profile)
        draft.checks = {**result.checks, "reasons": result.reasons}
        draft.updated_at = datetime.now(timezone.utc)

        if result.ok:
            draft.status = "pending"
            draft.fail_reason = ""
            passed += 1
            db.commit()
            continue

        if draft.generation < 2 and lead is not None:
            draft.generation += 1
            try:
                fresh = drafting._generate(db, lead, profile, draft.variant)
                draft.body = fresh.body
                draft.subject = fresh.subject
                draft.model = fresh.model
                db.commit()
                again = check_draft(db, draft, lead, profile)
                draft.checks = {**again.checks, "reasons": again.reasons}
                if again.ok:
                    draft.status = "pending"
                    draft.fail_reason = ""
                    passed += 1
                    regenerated += 1
                    db.commit()
                    continue
                draft.status = "needs_manual"
                draft.fail_reason = "; ".join(again.reasons)[:512]
                manual += 1
                db.commit()
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception("regeneration failed for draft %s", draft.id)
                draft.status = "needs_manual"
                draft.fail_reason = f"regeneration failed: {exc}"[:512]
                manual += 1
                db.commit()
                continue

        draft.status = "needs_manual"
        draft.fail_reason = "; ".join(result.reasons)[:512]
        failed += 1
        db.commit()

    return {
        "checked": len(pending),
        "passed": passed,
        "regenerated": regenerated,
        "needs_manual": manual + failed,
    }
