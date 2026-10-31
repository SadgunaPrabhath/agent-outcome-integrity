"""Unit tests for the StateReconciler — especially conflict handling."""

from __future__ import annotations

from engine.models import VerdictStatus, VerifierResult, VerifierStatus, VerifierType
from engine.reconciliation.reconciler import StateReconciler


def _r(vt: VerifierType, status: VerifierStatus, conf: float) -> VerifierResult:
    return VerifierResult(
        verifier_type=vt,
        postcondition_ref="p1",
        status=status,
        confidence=conf,
    )


def test_all_agree_satisfied():
    rec = StateReconciler()
    v = rec.reconcile(
        "p1",
        [
            _r(VerifierType.API, VerifierStatus.PASS, 1.0),
            _r(VerifierType.DOM, VerifierStatus.PASS, 0.7),
        ],
    )
    assert v.verdict is VerdictStatus.SATISFIED
    assert v.confidence == 1.0  # most authoritative agreeing source
    assert not v.conflict


def test_all_agree_violated():
    rec = StateReconciler()
    v = rec.reconcile("p1", [_r(VerifierType.API, VerifierStatus.FAIL, 1.0)])
    assert v.verdict is VerdictStatus.VIOLATED


def test_conflict_is_not_silently_resolved():
    """API says pass, DB says fail — must be CONFLICT, never SATISFIED."""
    rec = StateReconciler()
    v = rec.reconcile(
        "p1",
        [
            _r(VerifierType.API, VerifierStatus.PASS, 1.0),
            _r(VerifierType.DATABASE, VerifierStatus.FAIL, 1.0),
        ],
    )
    assert v.verdict is VerdictStatus.CONFLICT
    assert v.conflict is True
    assert v.confidence <= 0.3
    assert "CONFLICT" in v.reason


def test_no_conclusive_results_is_unknown():
    rec = StateReconciler()
    v = rec.reconcile(
        "p1", [_r(VerifierType.API, VerifierStatus.INCONCLUSIVE, 0.0)]
    )
    assert v.verdict is VerdictStatus.UNKNOWN
    assert v.confidence == 0.0


def test_presentational_does_not_mask_backend_failure():
    """DOM(pass) vs API(fail): the authoritative backend decides VIOLATED.

    The DOM disagreement is NOT a blocking conflict — it is exactly the false-
    completion signal, preserved in `contributing` for the classifier.
    """
    rec = StateReconciler()
    v = rec.reconcile(
        "p1",
        [
            _r(VerifierType.DOM, VerifierStatus.PASS, 0.7),
            _r(VerifierType.API, VerifierStatus.FAIL, 1.0),
        ],
    )
    assert v.verdict is VerdictStatus.VIOLATED
    assert v.conflict is False
    assert "presentational disagreement" in v.reason
    # both results retained for downstream classification
    assert len(v.contributing) == 2


def test_authoritative_sources_contradicting_is_conflict():
    """API(pass) vs DB(fail) — two authoritative sources disagree -> CONFLICT."""
    rec = StateReconciler()
    v = rec.reconcile(
        "p1",
        [
            _r(VerifierType.API, VerifierStatus.PASS, 1.0),
            _r(VerifierType.DATABASE, VerifierStatus.FAIL, 1.0),
        ],
    )
    assert v.verdict is VerdictStatus.CONFLICT
