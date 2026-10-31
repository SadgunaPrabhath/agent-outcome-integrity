"""OutcomeClassifier — reconciled verdicts -> task outcome + failure class.

Rules are deterministic and conservative. The guiding principles:
  * All postconditions satisfied  -> VERIFIED.
  * Any source conflict           -> never VERIFIED (UNKNOWN, or FAILED if a
                                     violation is also present).
  * Confirmed mix of pass/fail    -> PARTIAL.
  * Cannot read state             -> UNKNOWN (VERIFICATION_FAILURE), not FAILED.

Failure-class inference is heuristic but honest, and explicitly detects the
signature the whole project is about: agent + UI say success while a backend
source (API/DB) says the state never changed -> UI_FALSE_COMPLETION.
"""

from __future__ import annotations

from engine.models import (
    AgentClaim,
    FailureClass,
    Outcome,
    ReconciledVerdict,
    TaskOutcome,
    TaskSpec,
    VerdictStatus,
    VerifierStatus,
    VerifierType,
)


class OutcomeClassifier:
    def classify(
        self,
        verdicts: list[ReconciledVerdict],
        task: TaskSpec,
        claim: AgentClaim,
        *,
        http_status: int | None = None,
        exec_error: str | None = None,
    ) -> TaskOutcome:
        weights = {pc.ref: pc.weight for pc in task.expected_postconditions}
        total_weight = sum(weights.values()) or 1.0
        satisfied_weight = sum(
            weights.get(v.postcondition_ref, 0.0)
            for v in verdicts
            if v.verdict is VerdictStatus.SATISFIED
        )

        statuses = {v.verdict for v in verdicts}
        has_conflict = VerdictStatus.CONFLICT in statuses
        has_violation = VerdictStatus.VIOLATED in statuses
        has_satisfied = VerdictStatus.SATISFIED in statuses
        has_unknown = VerdictStatus.UNKNOWN in statuses
        all_satisfied = bool(verdicts) and statuses == {VerdictStatus.SATISFIED}

        outcome, reason = self._decide(
            all_satisfied, has_conflict, has_violation, has_satisfied, has_unknown
        )
        failure_class = (
            None
            if outcome is Outcome.VERIFIED
            else self._infer_failure(outcome, verdicts, claim, http_status, exec_error)
        )
        confidence = self._confidence(outcome, verdicts)

        return TaskOutcome(
            outcome=outcome,
            failure_class=failure_class,
            agent_claim=claim,
            verdicts=verdicts,
            confidence=confidence,
            satisfied_weight=satisfied_weight,
            total_weight=total_weight,
            reason=reason,
        )

    @staticmethod
    def _decide(
        all_satisfied: bool,
        has_conflict: bool,
        has_violation: bool,
        has_satisfied: bool,
        has_unknown: bool,
    ) -> tuple[Outcome, str]:
        if all_satisfied:
            return Outcome.VERIFIED, "All postconditions independently verified."
        if has_conflict:
            if has_violation:
                return (
                    Outcome.FAILED,
                    "Sources conflict and at least one postcondition is violated.",
                )
            return (
                Outcome.UNKNOWN,
                "Sources disagree; cannot confirm the requested state.",
            )
        if has_satisfied and has_violation:
            return Outcome.PARTIAL, "Some postconditions succeeded, others failed."
        if has_violation and not has_satisfied and not has_unknown:
            return Outcome.FAILED, "All checkable postconditions are violated."
        if has_violation:
            return Outcome.PARTIAL, "Mixed violations and unresolved postconditions."
        # only UNKNOWN (+ maybe satisfied) remain
        return (
            Outcome.UNKNOWN,
            "Insufficient evidence to confirm all postconditions.",
        )

    @staticmethod
    def _infer_failure(
        outcome: Outcome,
        verdicts: list[ReconciledVerdict],
        claim: AgentClaim,
        http_status: int | None = None,
        exec_error: str | None = None,
    ) -> FailureClass:
        if any(v.conflict for v in verdicts):
            return FailureClass.STATE_CONFLICT

        # Execution-level signals (from the trace) pin down transport failures
        # that a state read alone cannot distinguish.
        if http_status in (401, 403):
            return FailureClass.AUTH_FAILURE
        if http_status in (408, 504) or (exec_error and "timeout" in exec_error.lower()):
            return FailureClass.TIMEOUT
        if http_status is not None and http_status >= 500:
            return FailureClass.BACKEND_FAILURE
        if exec_error and http_status is None:
            return FailureClass.NETWORK_FAILURE

        # UI_FALSE_COMPLETION signature: a presentational source reports PASS
        # while a backend source (API/DB) reports FAIL for the *same*
        # postcondition. DOM co-verifies field postconditions, so it is the
        # source that can share a verdict with the backend. (A VISUAL_MATCH is a
        # pixel assertion routed to its own postcondition, so screenshot-level
        # false completion surfaces at the task level below, not here.)
        for v in verdicts:
            dom_pass = any(
                r.verifier_type is VerifierType.DOM and r.status is VerifierStatus.PASS
                for r in v.contributing
            )
            backend_fail = any(
                r.verifier_type in (VerifierType.API, VerifierType.DATABASE)
                and r.status is VerifierStatus.FAIL
                for r in v.contributing
            )
            if dom_pass and backend_fail and claim.claimed_success:
                return FailureClass.UI_FALSE_COMPLETION

        # Distinguish "wrong value persisted" from "nothing persisted".
        for v in verdicts:
            if v.verdict is VerdictStatus.VIOLATED:
                backend_results = [
                    r
                    for r in v.contributing
                    if r.verifier_type in (VerifierType.API, VerifierType.DATABASE)
                ]
                if any(r.observed not in (None, "", [], {}) for r in backend_results):
                    return FailureClass.WRONG_VALUE
                if backend_results:
                    return FailureClass.PERSISTENCE_FAILURE

        if outcome is Outcome.UNKNOWN:
            return FailureClass.VERIFICATION_FAILURE
        return FailureClass.BACKEND_FAILURE

    @staticmethod
    def _confidence(outcome: Outcome, verdicts: list[ReconciledVerdict]) -> float:
        if not verdicts:
            return 0.0
        if outcome is Outcome.VERIFIED:
            sat = [v.confidence for v in verdicts if v.verdict is VerdictStatus.SATISFIED]
            return min(sat) if sat else 0.0  # weakest link
        if outcome is Outcome.FAILED:
            viol = [v.confidence for v in verdicts if v.verdict is VerdictStatus.VIOLATED]
            return max(viol) if viol else 0.5
        if outcome is Outcome.PARTIAL:
            return sum(v.confidence for v in verdicts) / len(verdicts)
        # UNKNOWN
        return min(v.confidence for v in verdicts)
