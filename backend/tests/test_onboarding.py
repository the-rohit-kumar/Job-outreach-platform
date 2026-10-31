from __future__ import annotations

from fastapi.testclient import TestClient


def test_checklist_seeded(authed: TestClient) -> None:
    r = authed.get("/api/onboarding")
    assert r.status_code == 200
    keys = [i["key"] for i in r.json()]
    assert keys == ["profile", "gmail", "sources", "extension", "first_review"]


def test_profile_item_auto_marks_done(authed: TestClient) -> None:
    authed.get("/api/onboarding")
    items = {i["key"]: i for i in authed.get("/api/onboarding").json()}
    assert items["profile"]["auto"] is True
    assert items["profile"]["done"] is True


def test_manual_item_toggles_and_unknown_404(authed: TestClient) -> None:
    r = authed.patch("/api/onboarding/gmail", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True

    assert authed.patch("/api/onboarding/nope", json={"done": True}).status_code == 404


def test_auto_item_ignores_manual_override(authed: TestClient) -> None:
    # `extension` is auto-derived; with no token ever used it stays False.
    r = authed.patch("/api/onboarding/extension", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is False


def test_reset_clears_manual_items_only(authed: TestClient) -> None:
    authed.patch("/api/onboarding/gmail", json={"done": True})
    authed.post("/api/onboarding/reset")
    items = {i["key"]: i for i in authed.get("/api/onboarding").json()}
    assert items["gmail"]["done"] is False
    assert items["profile"]["done"] is True
