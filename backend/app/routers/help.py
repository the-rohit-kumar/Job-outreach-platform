"""Help page: USER_MANUAL.md rendered in-app, split into searchable sections."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_user

router = APIRouter(prefix="/api/help", tags=["help"], dependencies=[Depends(get_current_user)])


class Section(BaseModel):
    title: str
    body: str
    level: int


class HelpOut(BaseModel):
    markdown: str
    sections: list[Section]
    updated: str = ""


def _read_manual() -> tuple[str, str]:
    from ..config import REPO_ROOT

    candidates = [REPO_ROOT / "USER_MANUAL.md", Path(__file__).resolve().parents[3] / "USER_MANUAL.md"]
    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8"), str(path)
        except OSError:
            continue
    return "# Manual not found\n\nUSER_MANUAL.md is missing from the repository root.", ""


def _split(markdown: str) -> list[Section]:
    sections: list[Section] = []
    title = "Introduction"
    level = 1
    buffer: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if match:
            if buffer and title:
                sections.append(Section(title=title, body="\n".join(buffer).strip(), level=level))
            title = match.group(2).strip()
            level = len(match.group(1))
            buffer = []
        else:
            buffer.append(line)
    if buffer and title:
        sections.append(Section(title=title, body="\n".join(buffer).strip(), level=level))
    return [s for s in sections if s.body or s.level <= 2]


@router.get("", response_model=HelpOut)
def help_page() -> HelpOut:
    markdown, path = _read_manual()
    return HelpOut(markdown=markdown, sections=_split(markdown), updated=path)
