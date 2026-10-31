from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest

# Use a throwaway database and cache for every test run.
_TMP = Path(tempfile.mkdtemp(prefix="outreachhub-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["APP_SECRET"] = "test-secret"
os.environ["CACHE_DIR"] = str(_TMP / "cache")
os.environ["OUTREACH_SCHEDULER"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""  # tests always run in deterministic fallback mode
os.environ["LLM_PROVIDER"] = "anthropic"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import SessionLocal, init_models  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def make_transport(mapping: dict):
    """httpx.MockTransport serving recorded fixtures.

    mapping: {url_substring: status | (status, body) | (status, body, content_type)}
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, spec in mapping.items():
            if key in url:
                if isinstance(spec, tuple):
                    status, body = spec[0], spec[1]
                    content_type = spec[2] if len(spec) > 2 else None
                else:
                    status, body, content_type = spec, None, None
                if isinstance(body, (dict, list)):
                    return httpx.Response(
                        status,
                        json=body,
                        request=request,
                    )
                if body is None:
                    return httpx.Response(status, json={}, request=request)
                if isinstance(body, bytes):
                    return httpx.Response(
                        status, content=body, headers={"content-type": content_type or "application/octet-stream"},
                        request=request,
                    )
                ctype = content_type or ("text/html" if str(body).lstrip().startswith("<") else "application/json")
                return httpx.Response(
                    status, text=str(body), headers={"content-type": ctype}, request=request
                )
        return httpx.Response(404, json={"error": f"no fixture for {url}"}, request=request)

    return httpx.MockTransport(handler)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    init_models()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def authed(client):
    body = {"username": "rohit", "password": "correct-horse-1"}
    if client.post("/api/auth/setup", json=body).status_code != 200:
        assert client.post("/api/auth/login", json=body).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    return client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


from fastapi.testclient import TestClient  # noqa: E402
