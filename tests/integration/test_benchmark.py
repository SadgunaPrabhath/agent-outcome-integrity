"""Benchmark smoke + invariant tests.

Locks the two properties the project's credibility rests on:
  * AOIE catches 100% of the true false-completions (detection_rate == 1.0), and
  * AOIE never marks a truly-failed task VERIFIED (no false 'VERIFIED').
"""

from __future__ import annotations

import pytest

from benchmark.metrics import compute_metrics
from benchmark.runners import BenchmarkRunner, browser_factory
from benchmark.tasks import browser_drivable_catalog


@pytest.mark.asyncio
async def test_benchmark_runs_and_detects_all_false_completions():
    records = await BenchmarkRunner().run()
    assert len(records) > 20  # full matrix executed

    metrics = compute_metrics(records)
    # Every true failure that the agent claimed as success must be caught.
    assert metrics.detection_rate == 1.0

    # AOIE must never certify a truly-failed task as VERIFIED.
    for r in records:
        if r.ground_truth == "failed":
            assert r.aoie_outcome != "VERIFIED", (r.task_id, r.scenario)


@pytest.mark.asyncio
async def test_agents_apparent_success_exceeds_verified():
    """The core thesis: apparent success is inflated versus verified success."""
    records = await BenchmarkRunner().run()
    metrics = compute_metrics(records)
    assert metrics.apparent_success_rate > metrics.verified_success_rate
    assert metrics.false_completion_rate and metrics.false_completion_rate > 0


@pytest.mark.asyncio
async def test_browser_agent_benchmark_holds_external_validity():
    """The detection property is not an artifact of the scripted agent: the
    browser agent (driving a real form, trusting the on-screen banner) shows the
    same gap and the same 100% detection over the drivable task subset."""
    runner = BenchmarkRunner(
        tasks=browser_drivable_catalog(), adapter_factory=browser_factory
    )
    records = await runner.run()
    assert records and all(r.adapter_name == "browser-ui" for r in records)

    metrics = compute_metrics(records)
    assert metrics.detection_rate == 1.0
    assert metrics.apparent_success_rate > metrics.verified_success_rate
    for r in records:
        if r.ground_truth == "failed":
            assert r.aoie_outcome != "VERIFIED", (r.task_id, r.scenario)
