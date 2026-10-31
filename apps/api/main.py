"""AOIE control-plane API (FastAPI).

Exposes the engine as a service: trigger runs against the demo environment, then
read back independently-verified outcomes, verification results, and evidence.
Typed request/response via Pydantic; OpenAPI docs at ``/docs``.

This is the API the dashboard consumes. It persists every run to SQLite so
results survive restarts and power the overview metrics.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from benchmark.service import catalog_summary, find_task, run_task_scenario
from benchmark.tasks import default_catalog
from environments.demo_app import Scenario
from persistence import RunRepository, init_db, session_scope

REPORTS_DIR = Path("benchmark/reports")


class RunRequest(BaseModel):
    task_id: str
    scenario: Scenario = Scenario.NONE


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_api_app() -> FastAPI:
    app = FastAPI(
        title="Agent Outcome Integrity Engine (AOIE)",
        version="0.1.0",
        description="Independent outcome-verification and recovery layer for AI agents.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return {"tasks": catalog_summary(), "scenarios": [s.value for s in Scenario]}

    @app.post("/runs")
    async def create_run(req: RunRequest) -> dict[str, Any]:
        task = find_task(req.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"unknown task_id {req.task_id!r}")
        result = await run_task_scenario(task, req.scenario)
        with session_scope() as session:
            RunRepository(session).save(result, scenario=req.scenario.value)
        return result.model_dump(mode="json")

    @app.get("/runs")
    def list_runs(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        with session_scope() as session:
            return {"runs": RunRepository(session).list_runs(limit=limit, offset=offset)}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        with session_scope() as session:
            run = RunRepository(session).get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/runs/{run_id}/verification")
    def get_verification(run_id: str) -> dict[str, Any]:
        with session_scope() as session:
            return {"results": RunRepository(session).get_verifications(run_id)}

    @app.get("/runs/{run_id}/evidence")
    def get_evidence(run_id: str) -> dict[str, Any]:
        with session_scope() as session:
            return {"evidence": RunRepository(session).get_evidence(run_id)}

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        with session_scope() as session:
            return RunRepository(session).aggregate_metrics()

    @app.post("/benchmark/run")
    async def run_benchmark() -> dict[str, Any]:
        for task in default_catalog():
            for scenario in task.scenarios:
                result = await run_task_scenario(task, scenario)
                with session_scope() as session:
                    RunRepository(session).save(result, scenario=scenario.value)
        with session_scope() as session:
            return RunRepository(session).aggregate_metrics()

    @app.get("/benchmark/latest")
    def latest_benchmark() -> dict[str, Any]:
        path = REPORTS_DIR / "latest.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="no benchmark report yet")
        return json.loads(path.read_text(encoding="utf-8"))

    return app


app = create_api_app()
