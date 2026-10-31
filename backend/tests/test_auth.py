from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_status_needs_setup_then_not(client: TestClient, db) -> None:
    from app.models import User

    db.query(User).delete()
    db.commit()

    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["needs_setup"] is True

    r = client.post("/api/auth/setup", json={"username": "Rohit", "password": "correct-horse-1"})
    assert r.status_code == 200
    assert r.json()["username"] == "rohit"

    r = client.get("/api/auth/status")
    assert r.json()["needs_setup"] is False
    assert r.json()["user"]["username"] == "rohit"


def test_setup_rejected_when_user_exists(client: TestClient) -> None:
    client.post("/api/auth/setup", json={"username": "rohit", "password": "correct-horse-1"})
    r = client.post("/api/auth/setup", json={"username": "other", "password": "correct-horse-2"})
    assert r.status_code == 409


def test_login_logout_and_me(client: TestClient) -> None:
    client.post("/api/auth/setup", json={"username": "rohit", "password": "correct-horse-1"})
    client.post("/api/auth/logout")

    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"username": "rohit", "password": "wrong-password"})
    assert r.status_code == 401

    r = client.post("/api/auth/login", json={"username": "rohit", "password": "correct-horse-1"})
    assert r.status_code == 200

    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "rohit"


def test_profile_requires_auth(client: TestClient) -> None:
    assert client.get("/api/profile").status_code == 401


def test_password_hash_is_not_reversible(db) -> None:
    from app.models import User
    from app.security import hash_password, verify_password

    hashed = hash_password("correct-horse-1")
    assert "correct-horse-1" not in hashed
    assert verify_password(hashed, "correct-horse-1")
    assert not verify_password(hashed, "nope-nope-nope")
    db.query(User).delete()
    db.commit()
