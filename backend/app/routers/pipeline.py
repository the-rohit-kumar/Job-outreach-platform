"""Pipeline trigger + status (scheduled runs also happen automatically)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import CollectorRun, Lead, utcnow
from ..services import collector_runner, pipeline

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"], dependencies=[Depends(get_current_user)])


class RunIn(BaseModel):
    stages: list[str] = ["collect", "dedupe", "score", "enrich", "draft", "self_check"]


@router.post("/run")
def run_pipeline(body: RunIn, db: Session = Depends(get_db)) -> dict:
    summary: dict = {"stages": {}}
    collect = []
    if "collect" in body.stages:
        results = collector_runner.run_enabled(db, force=True)
        collect = [
            {"key": r.key, "status": r.status, "found": r.found, "new": r.new, "error": r.error}
            for r in results
        ]
        summary["collect"] = collect
        summary["new_leads"] = sum(r.new for r in results)
    stages = [s for s in body.stages if s != "collect"]
    summary.update(pipeline.run(db, stages=stages))
    summary["counts"] = collector_runner.lead_counts(db)
    return summary


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    runs = db.query(CollectorRun).order_by(CollectorRun.id.desc()).limit(30).all()
    from ..models import Draft

    return {
        "leads": collector_runner.lead_counts(db),
        "drafts": _count_drafts(db),
        "recent_runs": [
            {
                "id": r.id,
                "collector": r.collector_key,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "status": r.status,
                "found": r.leads_found,
                "new": r.leads_new,
                "error": r.error,
            }
            for r in runs
        ],
        "last_full_run": _last_full_run(db),
    }


def _count_drafts(db: Session) -> dict:
    from ..models import Draft

    rows = db.query(Draft.status, Draft.id).all()
    out: dict[str, int] = {}
    for status, _ in rows:
        out[status] = out.get(status, 0) + 1
    return out


def _last_full_run(db: Session) -> str | None:
    row = (
        db.query(CollectorRun)
        .filter(CollectorRun.status.in_(("ok", "partial", "error")))
        .order_by(CollectorRun.id.desc())
        .first()
    )
    return row.started_at.isoformat() if row else None
