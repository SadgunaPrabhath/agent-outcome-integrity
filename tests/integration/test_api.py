"""Integration tests for the FastAPI control-plane API + persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import persistence.database as db


@pytest.fixture
def client(tmp_path: Path):
    db.configure(f"sqlite:///{tmp_path / 'api_test.db'}")
    from apps.api.main import create_api_app

    with TestClient(create_api_app()) as c:
        yield c


def test_catalog_lists_tasks_and_scenarios(client):
    resp = client.get("/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["task_id"] == "profile_name" for t in data["tasks"])
    assert "fail_backend_write" in data["scenarios"]


def test_run_false_completion_flows_through_api(client):
    resp = client.post(
        "/runs", json={"task_id": "profile_name", "scenario": "fail_backend_write"}
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["agent_claim"]["claimed_success"] is True
    assert result["final_outcome"]["outcome"] == "FAILED"
    assert result["final_outcome"]["failure_class"] == "UI_FALSE_COMPLETION"

    run_id = result["run_id"]
    # persisted and listable
    listing = client.get("/runs").json()["runs"]
    assert any(r["run_id"] == run_id for r in listing)

    # detail, verification, evidence
    assert client.get(f"/runs/{run_id}").json()["run_id"] == run_id
    verifs = client.get(f"/runs/{run_id}/verification").json()["results"]
    assert len(verifs) >= 2  # API + DB + DOM
    evidence = client.get(f"/runs/{run_id}/evidence").json()["evidence"]
    assert len(evidence) >= 1


def test_run_honest_success_is_verified(client):
    resp = client.post("/runs", json={"task_id": "profile_name", "scenario": "none"})
    assert resp.json()["final_outcome"]["outcome"] == "VERIFIED"


def test_metrics_aggregate(client):
    client.post("/runs", json={"task_id": "profile_name", "scenario": "none"})
    client.post("/runs", json={"task_id": "profile_name", "scenario": "fail_backend_write"})
    metrics = client.get("/metrics").json()
    assert metrics["total_runs"] >= 2
    assert 0.0 <= metrics["verified_success_rate"] <= 1.0


def test_unknown_task_404(client):
    assert client.post("/runs", json={"task_id": "nope", "scenario": "none"}).status_code == 404
