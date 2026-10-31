"""End-to-end engine tests (no browser): sources -> verify -> reconcile."""

from __future__ import annotations

import pytest

from engine.classification.classifier import OutcomeClassifier
from engine.execution.context import RunContext
from engine.models import (
    AgentClaim,
    FailureClass,
    Outcome,
    Postcondition,
    PostconditionType,
    TargetRef,
    TaskSpec,
    TemporalSpec,
    VerdictStatus,
    VerifierType,
)
from engine.observation.inmemory import InMemoryStateSource
from engine.verification.engine import VerificationEngine


def _task(temporal: TemporalSpec | None = None) -> TaskSpec:
    return TaskSpec(
        task_id="profile_update_001",
        description="Change profile name to Alice",
        target=TargetRef(entity="user_profile"),
        expected_postconditions=[
            Postcondition(
                ref="name_is_alice",
                type=PostconditionType.FIELD_EQUALS,
                entity="user_profile",
                field="name",
                expected="Alice",
                temporal=temporal,
            )
        ],
    )


async def _run(ctx: RunContext):
    report = await VerificationEngine().verify(ctx)
    outcome = OutcomeClassifier().classify(
        report.verdicts, ctx.task, AgentClaim(claimed_success=True)
    )
    return report, outcome


@pytest.mark.asyncio
async def test_verified_when_all_sources_agree():
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Alice"}))
    ctx.register_source(InMemoryStateSource(VerifierType.DOM, {"name": "Alice"}))
    _, outcome = await _run(ctx)
    assert outcome.outcome is Outcome.VERIFIED
    assert outcome.false_completion is False


@pytest.mark.asyncio
async def test_false_completion_ui_success_backend_unchanged():
    """The headline demo: UI shows Alice, backend still Bob, agent claims done.

    The authoritative API decides VIOLATED; the DOM 'success' is the false-
    completion signal, so the outcome is FAILED / UI_FALSE_COMPLETION.
    """
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.DOM, {"name": "Alice"}))
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Bob"}))
    report, outcome = await _run(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.VIOLATED
    assert outcome.outcome is Outcome.FAILED
    assert outcome.failure_class is FailureClass.UI_FALSE_COMPLETION
    assert outcome.false_completion is True


@pytest.mark.asyncio
async def test_authoritative_conflict_is_unknown():
    """API and DB (both authoritative) disagree -> CONFLICT -> UNKNOWN."""
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Alice"}))
    ctx.register_source(InMemoryStateSource(VerifierType.DATABASE, {"name": "Bob"}))
    report, outcome = await _run(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.CONFLICT
    assert outcome.outcome is Outcome.UNKNOWN
    assert outcome.failure_class is FailureClass.STATE_CONFLICT


@pytest.mark.asyncio
async def test_persistence_failure_backend_only():
    """Only a backend source, and it never got the write -> FAILED."""
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Bob"}))
    _, outcome = await _run(ctx)
    assert outcome.outcome is Outcome.FAILED
    assert outcome.failure_class is FailureClass.WRONG_VALUE
    assert outcome.false_completion is True


@pytest.mark.asyncio
async def test_unknown_when_source_errors():
    ctx = RunContext(task=_task())
    ctx.register_source(
        InMemoryStateSource(VerifierType.API, {}, error="connection refused")
    )
    _, outcome = await _run(ctx)
    assert outcome.outcome is Outcome.UNKNOWN
    assert outcome.failure_class is FailureClass.VERIFICATION_FAILURE


@pytest.mark.asyncio
async def test_temporal_within_eventual_consistency():
    """State starts wrong then becomes correct; within-window verifier waits."""
    src = InMemoryStateSource(
        VerifierType.API,
        sequence=[{"name": "Bob"}, {"name": "Bob"}, {"name": "Alice"}],
    )
    ctx = RunContext(task=_task(TemporalSpec(within_s=5, poll_interval_s=0.01)))
    ctx.register_source(src)
    _, outcome = await _run(ctx)
    assert outcome.outcome is Outcome.VERIFIED


@pytest.mark.asyncio
async def test_temporal_must_hold_fails_if_reverts():
    """State is right, then reverts within the hold window -> not verified."""
    src = InMemoryStateSource(
        VerifierType.API,
        sequence=[{"name": "Alice"}, {"name": "Alice"}, {"name": "Bob"}],
    )
    ctx = RunContext(task=_task(TemporalSpec(must_hold_s=5, poll_interval_s=0.01)))
    ctx.register_source(src)
    _, outcome = await _run(ctx)
    assert outcome.outcome is not Outcome.VERIFIED
