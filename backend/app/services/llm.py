"""LLM access: Anthropic by default, cost tracking, daily spend cap.

If no API key is configured (or the cap is hit) every call raises
``LLMUnavailable``; callers fall back to deterministic behaviour and clearly
label results as fallback so the UI can show it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..config import settings
from ..models import UsageEvent

logger = logging.getLogger("outreachhub.llm")

API_URL = "https://api.anthropic.com/v1/messages"

# USD per million tokens (input, output). Approximate published prices.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-3-7-sonnet-20250219": (3.0, 15.0),
}
DEFAULT_PRICE = (3.0, 15.0)


class LLMUnavailable(RuntimeError):
    """No key, provider disabled, or daily spend cap reached."""


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


def _day_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def spend_today(db) -> float:
    from sqlalchemy import func

    from ..models import UsageEvent as U

    total = (
        db.query(func.coalesce(func.sum(U.cost_usd), 0.0))
        .filter(U.day_key == _day_key())
        .scalar()
    )
    return float(total or 0.0)


def _daily_cap_usd(db) -> float:
    from ..models import Setting

    row = db.get(Setting, "llm.spend_cap_usd")
    if row is not None and row.value is not None:
        try:
            return float(row.value)
        except (TypeError, ValueError):
            pass
    return float(settings.llm_daily_spend_cap_usd)


def provider_ready() -> tuple[bool, str]:
    if settings.llm_provider.lower() in ("none", "off", "disabled"):
        return False, "LLM_PROVIDER is set to none"
    if not settings.anthropic_api_key:
        return False, "ANTHROPIC_API_KEY is not configured (running in fallback mode)"
    return True, ""


def complete(
    db,
    *,
    system: str,
    user: str,
    purpose: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
) -> LLMResult:
    """Single chat completion. Raises LLMUnavailable when it cannot run."""
    ready, why = provider_ready()
    if not ready:
        raise LLMUnavailable(why)

    spend = spend_today(db)
    cap = _daily_cap_usd(db)
    if spend >= cap:
        raise LLMUnavailable(
            f"Daily LLM spend cap reached (${spend:.2f} of ${cap:.2f}). "
            "Raise llm.spend_cap_usd in Settings tomorrow."
        )

    model = model or settings.llm_fast_model
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        resp = httpx.post(API_URL, headers=headers, json=payload, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        _record(db, purpose, model, ok=False, error=str(exc.status_code))
        raise LLMUnavailable(f"Anthropic API error {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        _record(db, purpose, model, ok=False, error=str(exc))
        raise LLMUnavailable(f"Network error calling Anthropic: {exc}") from exc

    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    usage = data.get("usage", {})
    in_tokens = int(usage.get("input_tokens") or 0)
    out_tokens = int(usage.get("output_tokens") or 0)
    price_in, price_out = PRICING.get(model, DEFAULT_PRICE)
    cost = (in_tokens * price_in + out_tokens * price_out) / 1_000_000

    _record(
        db,
        purpose,
        model,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        cost_usd=cost,
        ok=True,
    )
    return LLMResult(text=text, model=model, input_tokens=in_tokens, output_tokens=out_tokens, cost_usd=cost)


def _record(
    db,
    purpose: str,
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    ok: bool = True,
    error: str = "",
) -> None:
    try:
        now = datetime.now(timezone.utc)
        db.add(
            UsageEvent(
                ts=now,
                day_key=_day_key(now),
                provider=settings.llm_provider,
                model=model,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=round(cost_usd, 6),
                ok=ok,
                error=error[:255],
            )
        )
        db.commit()
    except Exception:  # never fail a call because of bookkeeping
        logger.exception("Failed to record LLM usage")


def complete_json(db, **kwargs) -> dict:
    result = complete(db, **kwargs)
    return parse_json(result.text), result


def parse_json(text: str) -> dict:
    """Parse JSON even when the model wraps it in prose or code fences."""
    text = (text or "").strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start >= 0:
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            pass
    return {}
