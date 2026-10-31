from __future__ import annotations

from fastapi.testclient import TestClient


def test_token_created_once_and_authenticates(authed: TestClient) -> None:
    r = authed.post("/api/tokens", json={"name": "Chrome extension"})
    assert r.status_code == 200
    body = r.json()
    raw = body["raw_token"]
    assert raw.startswith("oh_")
    assert body["token"]["prefix"] == raw[:11]

    # The raw token is not returned again by the list endpoint.
    listed = authed.get("/api/tokens").json()
    assert len(listed) == 1
    assert "raw_token" not in listed[0]

    # Bearer auth works without a session cookie.
    fresh = TestClient(authed.app)
    r = fresh.get("/api/extension/ping", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Bad token is rejected.
    r = fresh.get("/api/extension/ping", headers={"Authorization": "Bearer oh_nope"})
    assert r.status_code == 401


def test_extension_ping_marks_onboarding_done(authed: TestClient) -> None:
    raw = authed.post("/api/tokens", json={"name": "ext"}).json()["raw_token"]
    fresh = TestClient(authed.app)
    fresh.get("/api/extension/ping", headers={"Authorization": f"Bearer {raw}"})
    items = {i["key"]: i for i in authed.get("/api/onboarding").json()}
    assert items["extension"]["done"] is True


def test_revoked_token_stops_working(authed: TestClient) -> None:
    created = authed.post("/api/tokens", json={"name": "temp"}).json()
    raw = created["raw_token"]
    token_id = created["token"]["id"]

    fresh = TestClient(authed.app)
    assert fresh.get("/api/extension/ping", headers={"Authorization": f"Bearer {raw}"}).status_code == 200

    assert authed.delete(f"/api/tokens/{token_id}").status_code == 200
    assert fresh.get("/api/extension/ping", headers={"Authorization": f"Bearer {raw}"}).status_code == 401


def test_extension_ping_requires_auth(client: TestClient) -> None:
    assert client.get("/api/extension/ping").status_code == 401
