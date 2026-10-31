"""Service helpers to execute a single catalog task under a scenario.

Shared by the benchmark runner and the API so a run is produced identically in
both. Each call gets its own isolated demo app + SQLite file so runs never
interfere.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx

from adapters.scripted import ScriptedHttpAdapter
from benchmark.tasks import BenchmarkTask, default_catalog
from engine.execution.context import RunContext
from engine.orchestrator import Orchestrator
from engine.orchestrator.result import RunResult
from environments.demo_app import Scenario, create_app
from environments.demo_app.wiring import demo_sources

BASE_URL = "http://testserver"


def find_task(task_id: str) -> BenchmarkTask | None:
    return next((t for t in default_catalog() if t.task_id == task_id), None)


def catalog_summary() -> list[dict]:
    return [
        {
            "task_id": t.task_id,
            "description": t.spec.description,
            "collection": t.collection,
            "record_id": t.record_id,
            "scenarios": [s.value for s in t.scenarios],
        }
        for t in default_catalog()
    ]


async def run_task_scenario(task: BenchmarkTask, scenario: Scenario) -> RunResult:
    tmpdir = tempfile.mkdtemp(prefix="aoie_run_")
    db_path = str(Path(tmpdir) / "demo.sqlite")
    app = create_app(db_path=db_path, timeout_delay_s=1.5)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post("/admin/reset")
        if task.seed_fields is not None:
            await client.post(
                "/admin/seed",
                json={
                    "collection": task.collection,
                    "record_id": task.record_id,
                    "fields": task.seed_fields,
                },
            )
        await client.post(
            "/admin/scenario",
            json={
                "collection": task.collection,
                "record_id": task.record_id,
                "scenario": scenario.value,
            },
        )
        ctx = RunContext(task=task.spec)
        for source in demo_sources(BASE_URL, db_path, client=client):
            ctx.register_source(source)
        adapter = ScriptedHttpAdapter(base_url=BASE_URL, client=client)
        return await Orchestrator(adapter).run(ctx)
