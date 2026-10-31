"""RunRepository — persist and query orchestrated runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.orchestrator.result import RunResult
from engine.tracing import redact
from persistence.models import (
    EvidenceRow,
    RecoveryAttemptRow,
    RunRow,
    VerificationResultRow,
)


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, result: RunResult, scenario: str | None = None) -> RunRow:
        row = RunRow(
            run_id=result.run_id,
            task_id=result.task_id,
            adapter_name=result.adapter_name,
            scenario=scenario,
            agent_claimed_success=result.agent_claim.claimed_success,
            final_outcome=result.final_outcome.outcome.value,
            failure_class=(
                result.final_outcome.failure_class.value
                if result.final_outcome.failure_class
                else None
            ),
            false_completion=result.false_completion,
            confidence=result.final_outcome.confidence,
            recovered=result.recovered,
            recovery_attempts=result.recovery_history.count,
            started_at=result.started_at,
            ended_at=result.ended_at,
            error=result.error,
            result_json=redact(result.model_dump(mode="json")),
        )

        # Normalized rows come from the final verification round.
        final_round = result.rounds[-1] if result.rounds else None
        if final_round is not None:
            for vr in final_round.report.results:
                row.verifications.append(
                    VerificationResultRow(
                        postcondition_ref=vr.postcondition_ref,
                        verifier_type=vr.verifier_type.value,
                        status=vr.status.value,
                        expected=_s(vr.expected),
                        observed=_s(vr.observed),
                        confidence=vr.confidence,
                        latency_ms=vr.latency_ms,
                        evidence_id=vr.evidence_id,
                    )
                )

        seen: set[str] = set()
        for ev in result.evidence:
            if ev.id in seen:
                continue
            seen.add(ev.id)
            row.evidences.append(
                EvidenceRow(
                    content_hash=ev.id,
                    verifier_type=ev.verifier_type.value,
                    source=ev.source,
                    expected_state=_s(ev.expected_state),
                    observed_state=_s(ev.observed_state),
                    confidence=ev.confidence,
                    payload_json=redact(ev.model_dump(mode="json")),
                )
            )

        for att in result.recovery_history.attempts:
            row.recoveries.append(
                RecoveryAttemptRow(
                    attempt_no=att.attempt_no,
                    strategy=att.strategy.value,
                    reason=att.reason,
                    idempotency_safe=att.idempotency_safe,
                    executed=att.executed,
                    outcome_after=att.outcome_after,
                )
            )

        self.session.merge(row)
        self.session.flush()
        return row

    # --- queries -------------------------------------------------------------
    def list_runs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        stmt = (
            select(RunRow)
            .order_by(RunRow.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_summary(r) for r in self.session.scalars(stmt)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.session.get(RunRow, run_id)
        return row.result_json if row else None

    def get_verifications(self, run_id: str) -> list[dict[str, Any]]:
        stmt = select(VerificationResultRow).where(VerificationResultRow.run_id == run_id)
        return [
            {
                "postcondition_ref": v.postcondition_ref,
                "verifier_type": v.verifier_type,
                "status": v.status,
                "expected": v.expected,
                "observed": v.observed,
                "confidence": v.confidence,
                "latency_ms": v.latency_ms,
                "evidence_id": v.evidence_id,
            }
            for v in self.session.scalars(stmt)
        ]

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        stmt = select(EvidenceRow).where(EvidenceRow.run_id == run_id)
        return [e.payload_json for e in self.session.scalars(stmt)]

    def aggregate_metrics(self) -> dict[str, Any]:
        rows = list(self.session.scalars(select(RunRow)))
        n = len(rows)
        if n == 0:
            return {"total_runs": 0}
        apparent = sum(r.agent_claimed_success for r in rows)
        verified = sum(r.final_outcome == "VERIFIED" for r in rows)
        false_completions = sum(r.false_completion for r in rows)
        outcome_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        for r in rows:
            outcome_counts[r.final_outcome] = outcome_counts.get(r.final_outcome, 0) + 1
            if r.failure_class:
                failure_counts[r.failure_class] = failure_counts.get(r.failure_class, 0) + 1
        return {
            "total_runs": n,
            "apparent_success_rate": round(apparent / n, 4),
            "verified_success_rate": round(verified / n, 4),
            "false_completion_rate": round(false_completions / apparent, 4) if apparent else None,
            "outcome_integrity": round(verified / n, 4),
            "recovered_runs": sum(r.recovered for r in rows),
            "outcome_counts": outcome_counts,
            "failure_class_counts": failure_counts,
        }


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _summary(r: RunRow) -> dict[str, Any]:
    return {
        "run_id": r.run_id,
        "task_id": r.task_id,
        "adapter_name": r.adapter_name,
        "scenario": r.scenario,
        "agent_claimed_success": r.agent_claimed_success,
        "final_outcome": r.final_outcome,
        "failure_class": r.failure_class,
        "false_completion": r.false_completion,
        "confidence": r.confidence,
        "recovered": r.recovered,
        "recovery_attempts": r.recovery_attempts,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
    }
