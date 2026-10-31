"""StateReconciler — combine multiple verifier results into one verdict.

Two disciplines, both essential to the project's thesis:

  1. *Authoritative sources decide.* DB/API/Network read persistent ground truth
     and determine SATISFIED/VIOLATED. A presentational source (DOM/Visual)
     reflects what the UI shows; it must never mask a clear backend result. So
     "DOM says done, API+DB say not done" resolves to VIOLATED (a false
     completion), not to an ambiguous conflict.

  2. *Genuine contradiction is never silently resolved.* When authoritative
     sources contradict *each other* (API says "Alice", DB says "Bob"), the
     verdict is CONFLICT — we refuse to assume success. Authority ordering only
     breaks ties within agreement; it never overrides a contradiction between
     two authoritative sources.

The DOM-vs-backend disagreement is preserved in ``contributing`` so the
OutcomeClassifier can label it UI_FALSE_COMPLETION.
"""

from __future__ import annotations

from engine.models import ReconciledVerdict, VerdictStatus, VerifierResult, VerifierStatus


class StateReconciler:
    CONFLICT_CONFIDENCE = 0.2

    def reconcile(
        self, postcondition_ref: str, results: list[VerifierResult]
    ) -> ReconciledVerdict:
        conclusive = [r for r in results if r.status is not VerifierStatus.INCONCLUSIVE]
        if not conclusive:
            return self._verdict(
                postcondition_ref, VerdictStatus.UNKNOWN, 0.0, results,
                "No conclusive verifier could read the relevant state.",
            )

        authoritative = [r for r in conclusive if r.verifier_type.is_authoritative]
        deciding = authoritative or conclusive  # fall back to presentational
        tier = "authoritative" if authoritative else "presentational"

        passed = [r for r in deciding if r.status is VerifierStatus.PASS]
        failed = [r for r in deciding if r.status is VerifierStatus.FAIL]

        if passed and failed:
            return self._verdict(
                postcondition_ref, VerdictStatus.CONFLICT, self.CONFLICT_CONFIDENCE,
                results, self._conflict_reason(tier, passed, failed), conflict=True,
            )

        if passed:
            return self._verdict(
                postcondition_ref, VerdictStatus.SATISFIED,
                max(r.confidence for r in passed), results,
                self._agree_reason(tier, "satisfied", passed, results),
            )

        return self._verdict(
            postcondition_ref, VerdictStatus.VIOLATED,
            max(r.confidence for r in failed), results,
            self._agree_reason(tier, "violated", failed, results),
        )

    @staticmethod
    def _verdict(
        ref: str,
        verdict: VerdictStatus,
        confidence: float,
        results: list[VerifierResult],
        reason: str,
        conflict: bool = False,
    ) -> ReconciledVerdict:
        return ReconciledVerdict(
            postcondition_ref=ref,
            verdict=verdict,
            confidence=confidence,
            conflict=conflict,
            contributing=results,
            reason=reason,
        )

    @staticmethod
    def _srcs(results: list[VerifierResult]) -> str:
        return ", ".join(sorted({r.verifier_type.value for r in results}))

    def _agree_reason(
        self,
        tier: str,
        word: str,
        deciding: list[VerifierResult],
        all_results: list[VerifierResult],
    ) -> str:
        base = f"{word} — {tier} sources agree ({self._srcs(deciding)})"
        # Note presentational disagreement (e.g. UI still shows success).
        deciding_status = deciding[0].status
        dissent = [
            r
            for r in all_results
            if not r.verifier_type.is_authoritative
            and r.status is not VerifierStatus.INCONCLUSIVE
            and r.status is not deciding_status
        ]
        if dissent and tier == "authoritative":
            base += f"; presentational disagreement from {self._srcs(dissent)}"
        return base

    def _conflict_reason(
        self, tier: str, passed: list[VerifierResult], failed: list[VerifierResult]
    ) -> str:
        return (
            f"STATE_CONFLICT — {tier} sources contradict: "
            f"{self._srcs(passed)} report satisfied while {self._srcs(failed)} "
            f"report violated; refusing to assume success."
        )
