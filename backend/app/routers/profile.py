from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Profile, utcnow
from ..schemas import ProfileIn, ProfileOut
from ..seed import DEFAULT_TONE
from ..services import onboarding as onboarding_service

router = APIRouter(prefix="/api/profile", tags=["profile"], dependencies=[Depends(get_current_user)])


def _get_profile(db: Session) -> Profile:
    profile = db.get(Profile, 1)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("", response_model=ProfileOut)
def read_profile(db: Session = Depends(get_db)) -> Profile:
    return _get_profile(db)


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileIn, db: Session = Depends(get_db)) -> Profile:
    profile = _get_profile(db)
    payload = body.model_dump()
    # Hard drafting rules and tone defaults are not negotiable: merge so an
    # update can never silently drop them.
    tone = dict(DEFAULT_TONE)
    tone.update(body.tone or {})
    if not tone.get("hard_rules"):
        tone["hard_rules"] = list(DEFAULT_TONE["hard_rules"])
    payload["tone"] = tone
    for field, value in payload.items():
        setattr(profile, field, value)
    profile.updated_at = utcnow()
    db.commit()
    db.refresh(profile)
    onboarding_service.set_done(db, "profile", True)
    return profile


@router.post("/resume")
async def upload_and_parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    from ..services import resume as resume_service

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.lower().split(".")[-1]
    if ext not in ("pdf", "txt", "md"):
        raise HTTPException(status_code=400, detail="Only .pdf, .txt, and .md files are supported")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        raw_text = resume_service.extract_text_from_file(content, file.filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to extract text from resume: {exc}")

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from uploaded file")

    parsed = resume_service.parse_resume(db, raw_text)

    # 1. Update Profile
    profile = _get_profile(db)
    if parsed.get("about_me"):
        profile.about_me = parsed["about_me"]
    if parsed.get("skills"):
        profile.skills = parsed["skills"]
    profile.cv_url = f"uploaded:{file.filename}"
    profile.updated_at = utcnow()
    db.commit()
    db.refresh(profile)

    # 2. Automatically update search filters across all collectors
    updated_sources = resume_service.sync_collector_search_filters(
        db, parsed.get("search_keywords", [])
    )

    onboarding_service.set_done(db, "profile", True)

    return {
        "ok": True,
        "filename": file.filename,
        "about_me": profile.about_me,
        "skills": profile.skills,
        "search_keywords": parsed.get("search_keywords", []),
        "updated_sources": updated_sources,
    }
