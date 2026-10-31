"""Pipeline orchestrator: DEDUPE -> SCORE -> ENRICH -> DRAFT -> SELF-CHECK.

COLLECT lives in collector_runner; REVIEW QUEUE is the human step; SEND/TRACK
and FOLLOW-UP are the scheduler's job. Everything here is idempotent: run it
as often as you like.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from . import dedupe, drafting, enrichment, scoring, self_check

logger = logging.getLogger("outreachhub.pipeline")

STAGES = ("dedupe", "score", "enrich", "draft", "self_check")


def run(db: Session, stages: Iterable[str] = STAGES, transport=None) -> dict:
    wanted = [s for s in stages if s in STAGES]
    summary: dict = {"stages": {}}
    for stage in wanted:
        try:
            if stage == "dedupe":
                summary["stages"]["dedupe"] = dedupe.run_dedupe(db)
            elif stage == "score":
                summary["stages"]["score"] = scoring.score_new_leads(db)
            elif stage == "enrich":
                summary["stages"]["enrich"] = enrichment.enrich_new(db, transport=transport)
            elif stage == "draft":
                summary["stages"]["draft"] = _draft_stage(db)
            elif stage == "self_check":
                summary["stages"]["self_check"] = self_check.run_self_check(db)
        except Exception as exc:  # noqa: BLE001 - one stage never kills the run
            logger.exception("Pipeline stage %s failed", stage)
            summary["stages"][stage] = {"error": f"{type(exc).__name__}: {exc}"}
    return summary


def _draft_stage(db: Session) -> dict:
    from ..models import Lead, Profile

    profile = db.get(Profile, 1)
    pending = (
        db.query(Lead)
        .filter(Lead.status == "enriched", Lead.duplicate_of.is_(None), Lead.opted_out.is_(False))
        .limit(300)
        .all()
    )
    created = 0
    for lead in pending:
        try:
            drafts = drafting.draft_lead(db, lead, profile)
            created += len(drafts)
        except Exception:  # noqa: BLE001
            logger.exception("Drafting failed for lead %s", lead.id)
    return {"candidates": len(pending), "drafts_created": created}
