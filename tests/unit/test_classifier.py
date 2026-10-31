"""Unit tests for OutcomeClassifier, including the false-completion signature."""

from __future__ import annotations

from engine.classification.classifier import OutcomeClassifier
from engine.models import (
    AgentClaim,
    FailureClass,
    Outcome,
    Postcondition,
    PostconditionType,
    ReconciledVerdict,
    TargetRef,
    TaskSpec,
    VerdictStatus,
    VerifierResult,
    VerifierStatus,
    VerifierType,
)


def _task(*refs: str) -> TaskSpec:
    return TaskSpec(
        task_id="t",
        description="d",
        target=TargetRef(entity="user"),
        expected_postconditions=[
            Postcondition(
                ref=r,
                type=PostconditionType.FIELD_EQUALS,
                entity="user",
                field="name",
                expected="Alice",
            )
            for r in refs
        ],
    )


def _verdict(ref: str, status: VerdictStatus, results=None, conf=1.0) -> ReconciledVerdict:
    return ReconciledVerdict(
        postcondition_ref=ref,
        verdict=status,
        confidence=conf,
        conflict=status is VerdictStatus.CONFLICT,
        contributing=results or [],
    )


def _res(vt, status, observed=None):
    return VerifierResult(
        verifier_type=vt,
        postcondition_ref="p1",
        status=status,
        observed=observed,
        confidence=1.0,
    )


def test_all_satisfied_is_verified():
    c = OutcomeClassifier()
    out = c.classify(
        [_verdict("p1", VerdictStatus.SATISFIED)],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.VERIFIED
    assert out.failure_class is None
    assert out.false_completion is False


def test_ui_false_completion_detected():
    """DOM passes, API fails, agent claimed success -> UI_FALSE_COMPLETION."""
    c = OutcomeClassifier()
    results = [
        _res(VerifierType.DOM, VerifierStatus.PASS, "Alice"),
        _res(VerifierType.API, VerifierStatus.FAIL, "Bob"),
    ]
    # DOM/API disagree -> reconciler would say CONFLICT; but the false-completion
    # case we target is DOM-only-pass with backend fail and agent claim.
    out = c.classify(
        [_verdict("p1", VerdictStatus.VIOLATED, results)],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.FAILED
    assert out.failure_class is FailureClass.UI_FALSE_COMPLETION
    assert out.false_completion is True


def test_state_conflict_yields_unknown_or_failed():
    c = OutcomeClassifier()
    out = c.classify(
        [_verdict("p1", VerdictStatus.CONFLICT)],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.UNKNOWN
    assert out.failure_class is FailureClass.STATE_CONFLICT


def test_partial_outcome():
    c = OutcomeClassifier()
    out = c.classify(
        [
            _verdict("p1", VerdictStatus.SATISFIED),
            _verdict("p2", VerdictStatus.VIOLATED, [_res(VerifierType.API, VerifierStatus.FAIL, None)]),
        ],
        _task("p1", "p2"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.PARTIAL


def test_persistence_failure_when_nothing_written():
    c = OutcomeClassifier()
    out = c.classify(
        [_verdict("p1", VerdictStatus.VIOLATED, [_res(VerifierType.API, VerifierStatus.FAIL, None)])],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.FAILED
    assert out.failure_class is FailureClass.PERSISTENCE_FAILURE


def test_wrong_value_when_something_else_written():
    c = OutcomeClassifier()
    out = c.classify(
        [_verdict("p1", VerdictStatus.VIOLATED, [_res(VerifierType.API, VerifierStatus.FAIL, "Bob")])],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.failure_class is FailureClass.WRONG_VALUE


def test_unknown_when_unverifiable():
    c = OutcomeClassifier()
    out = c.classify(
        [_verdict("p1", VerdictStatus.UNKNOWN, conf=0.0)],
        _task("p1"),
        AgentClaim(claimed_success=True),
    )
    assert out.outcome is Outcome.UNKNOWN
    assert out.failure_class is FailureClass.VERIFICATION_FAILURE
