"""BenchmarkRunner — execute the task × scenario matrix and collect records.

Runs entirely in-process against the demo app via httpx's ASGI transport, with a
real SQLite file so the DatabaseVerifier reads true ground truth. Every run is
independent: the app is reset and re-seeded, and the scenario is set, before the
scripted agent executes.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from adapters.base import AgentAdapter
from adapters.playwright import BrowserUiAdapter, HttpxPageDriver
from adapters.scripted import ScriptedHttpAdapter
from benchmark.scenarios import GROUND_TRUTH, GroundTruth
from benchmark.tasks import BenchmarkTask, default_catalog
from engine.execution.context import RunContext
from engine.models import Outcome
from engine.orchestrator import Orchestrator
from environments.demo_app import Scenario, create_app
from environments.demo_app.wiring import demo_sources

BASE_URL = "http://testserver"

# An adapter factory builds a fresh agent per run, bound to the in-process client.
AdapterFactory = Callable[[str, httpx.AsyncClient], AgentAdapter]


def scripted_factory(base_url: str, client: httpx.AsyncClient) -> AgentAdapter:
    """The naive HTTP agent (trusts the 2xx response)."""
    return ScriptedHttpAdapter(base_url=base_url, client=client)


def browser_factory(base_url: str, client: httpx.AsyncClient) -> AgentAdapter:
    """The browser agent (trusts the on-screen banner), driven browser-free."""
    return BrowserUiAdapter(driver=HttpxPageDriver(base_url=base_url, client=client),
                            base_url=base_url)


@dataclass
class BenchmarkRecord:
    task_id: str
    scenario: str
    adapter_name: str
    ground_truth: str
    agent_claimed_success: bool
    aoie_outcome: str
    failure_class: str | None
    false_completion: bool
    recovered: bool
    recovery_attempts: int
    verification_latency_ms: int
    # Detection accuracy vs ground truth:
    caught: bool  # ground-truth failure that AOIE did NOT mark VERIFIED
    correct: bool  # AOIE verdict matches ground truth (VERIFIED iff succeeded)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class BenchmarkRunner:
    def __init__(
        self,
        tasks: list[BenchmarkTask] | None = None,
        adapter_factory: AdapterFactory = scripted_factory,
    ) -> None:
        self.tasks = tasks or default_catalog()
        self.adapter_factory = adapter_factory

    async def run(self) -> list[BenchmarkRecord]:
        tmpdir = tempfile.mkdtemp(prefix="aoie_bench_")
        db_path = str(Path(tmpdir) / "demo.sqlite")
        app = create_app(db_path=db_path, timeout_delay_s=1.5)
        transport = httpx.ASGITransport(app=app)
        records: list[BenchmarkRecord] = []
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            for task in self.tasks:
                for scenario in task.scenarios:
                    records.append(await self._run_one(client, db_path, task, scenario))
        return records

    async def _run_one(
        self,
        client: httpx.AsyncClient,
        db_path: str,
        task: BenchmarkTask,
        scenario: Scenario,
    ) -> BenchmarkRecord:
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
        adapter = self.adapter_factory(BASE_URL, client)
        result = await Orchestrator(adapter).run(ctx)

        gt = GROUND_TRUTH[scenario]
        verified = result.final_outcome.outcome is Outcome.VERIFIED
        caught = gt is GroundTruth.FAILED and not verified
        correct = verified == (gt is GroundTruth.SUCCEEDED)
        latency = result.rounds[0].report.total_latency_ms if result.rounds else 0

        return BenchmarkRecord(
            task_id=task.task_id,
            scenario=scenario.value,
            adapter_name=adapter.name,
            ground_truth=gt.value,
            agent_claimed_success=result.agent_claim.claimed_success,
            aoie_outcome=result.final_outcome.outcome.value,
            failure_class=(
                result.final_outcome.failure_class.value
                if result.final_outcome.failure_class
                else None
            ),
            false_completion=result.false_completion,
            recovered=result.recovered,
            recovery_attempts=result.recovery_history.count,
            verification_latency_ms=latency,
            caught=caught,
            correct=correct,
        )
