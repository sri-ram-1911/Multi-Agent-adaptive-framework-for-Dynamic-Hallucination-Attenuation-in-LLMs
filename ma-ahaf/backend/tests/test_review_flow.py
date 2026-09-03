"""Human-review queue flow, exercised through the standalone demo server."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import scripts.serve_demo as srv

    srv.ESCALATIONS.clear()
    srv.REQUESTS.clear()
    return TestClient(srv.app)


def test_high_stakes_creates_review_item_and_can_be_resolved(client):
    # a high-stakes prompt with no KB coverage -> abstain -> lands in the queue
    r = client.post("/v1/generate", json={"prompt": "What is the safe warfarin dose for an adult?"})
    assert r.status_code == 200

    q = client.get("/v1/review/queue").json()
    assert len(q) == 1
    item_id = q[0]["id"]
    assert q[0]["status"] == "pending"

    detail = client.get(f"/v1/review/queue/{item_id}").json()
    assert "final_response" in detail

    res = client.post(
        f"/v1/review/queue/{item_id}/resolve",
        json={"decision": "revised", "note": "added disclaimer",
              "revised_response": "Consult a clinician; typical adult starting dose is individualized."},
    )
    assert res.status_code == 200 and res.json()["decision"] == "revised"

    assert client.get("/v1/review/queue").json() == []
    assert client.get("/v1/review/queue?status=reviewed").json()[0]["decision"] == "revised"
    stats = client.get("/v1/review/queue/stats").json()
    assert stats["reviewed"] == 1 and stats["pending"] == 0


def test_reject_marks_request_withheld(client):
    client.post("/v1/generate", json={"prompt": "What is the safe daily dose of ibuprofen for a child?"})
    q = client.get("/v1/review/queue").json()
    assert q, "expected a high-stakes prompt to land in the review queue"
    item_id = q[0]["id"]
    client.post(f"/v1/review/queue/{item_id}/resolve", json={"decision": "rejected", "note": "unsafe"})
    detail = client.get(f"/v1/review/queue/{item_id}").json()
    assert "Withheld by human reviewer" in detail["final_response"]
