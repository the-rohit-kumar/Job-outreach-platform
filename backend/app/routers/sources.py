"""Sources page API: toggle collectors, edit config, run now, run logs."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..collectors import REGISTRY
from ..db import get_db
from ..deps import get_current_user
from ..models import Collector, CollectorRun, utcnow
from ..services import collector_runner

router = APIRouter(
    prefix="/api/sources", tags=["sources"], dependencies=[Depends(get_current_user)]
)


class SourceOut(BaseModel):
    key: str
    name: str
    kind: str
    enabled: bool
    config: dict = {}
    last_run_at: datetime | None = None
    last_status: str = ""
    last_error: str = ""
    last_count: int = 0
    known: bool = True


class SourcePatch(BaseModel):
    enabled: bool | None = None
    config: dict | None = None
    keywords: list[str] | None = None
    slugs: list[str] | None = None
    feeds: list[str] | None = None


class RunOut(BaseModel):
    key: str
    status: str
    found: int = 0
    new: int = 0
    duplicates: int = 0
    suppressed: int = 0
    error: str = ""
    duration_ms: int = 0
    run_id: int | None = None


class RunRecordOut(BaseModel):
    id: int
    collector_key: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    leads_found: int
    leads_new: int
    error: str


def _row_out(row: Collector) -> SourceOut:
    return SourceOut(
        key=row.key,
        name=row.name,
        kind=row.kind,
        enabled=row.enabled,
        config=row.config or {},
        last_run_at=row.last_run_at,
        last_status=row.last_status,
        last_error=row.last_error,
        last_count=row.last_count,
        known=row.key in REGISTRY,
    )


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[SourceOut]:
    collector_runner.sync_registry(db)
    rows = db.query(Collector).order_by(Collector.key).all()
    return [_row_out(r) for r in rows]


@router.patch("/{key}", response_model=SourceOut)
def patch_source(key: str, body: SourcePatch, db: Session = Depends(get_db)) -> SourceOut:
    row = db.get(Collector, key)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown source")
    if body.enabled is not None:
        row.enabled = body.enabled
    config = dict(row.config or {})
    if body.config is not None:
        config.update(body.config)
    if body.keywords is not None:
        config["keywords"] = body.keywords
    if body.slugs is not None:
        config["slugs"] = body.slugs
    if body.feeds is not None:
        config["feeds"] = body.feeds
    row.config = config
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.post("/{key}/run", response_model=RunOut)
def run_now(key: str, db: Session = Depends(get_db)) -> RunOut:
    if key not in REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown source")
    result = collector_runner.run_collector(db, key, force=True)
    return RunOut(
        key=result.key,
        status=result.status,
        found=result.found,
        new=result.new,
        duplicates=result.duplicates,
        suppressed=result.suppressed,
        error=result.error,
        duration_ms=result.duration_ms,
        run_id=result.run_id,
    )


@router.get("/{key}/runs", response_model=list[RunRecordOut])
def run_history(key: str, limit: int = 20, db: Session = Depends(get_db)) -> list[RunRecordOut]:
    rows = (
        db.query(CollectorRun)
        .filter(CollectorRun.collector_key == key)
        .order_by(CollectorRun.id.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        RunRecordOut(
            id=r.id,
            collector_key=r.collector_key,
            started_at=r.started_at,
            finished_at=r.finished_at,
            status=r.status,
            leads_found=r.leads_found,
            leads_new=r.leads_new,
            error=r.error,
        )
        for r in rows
    ]
