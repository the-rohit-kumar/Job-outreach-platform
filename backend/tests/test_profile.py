from __future__ import annotations

from fastapi.testclient import TestClient


def test_profile_seeded_and_updatable(authed: TestClient) -> None:
    r = authed.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Rohit Kumar"
    assert "SAP" in body["do_not_mention"]
    assert "LangGraph" in body["skills"]

    r = authed.put(
        "/api/profile",
        json={
            "display_name": "Rohit Kumar",
            "email": "rohit@example.com",
            "location": "Bengaluru, India (IST)",
            "about_me": "x" * 120,
            "skills": ["Python", "LangChain"],
            "do_not_mention": ["SAP", "Client names"],
            "tone": {"style": "conversational"},
        },
    )
    assert r.status_code == 200
    assert r.json()["email"] == "rohit@example.com"
    assert r.json()["skills"] == ["Python", "LangChain"]


def test_hard_drafting_rules_survive_updates(authed: TestClient) -> None:
    r = authed.put("/api/profile", json={"do_not_mention": ["SAP"]})
    assert r.status_code == 200
    assert "SAP" in r.json()["do_not_mention"]

    r = authed.get("/api/profile")
    assert any("Wipro-internal details" in rule for rule in r.json()["tone"]["hard_rules"])
    assert any("SAP" in rule for rule in r.json()["tone"]["hard_rules"])
