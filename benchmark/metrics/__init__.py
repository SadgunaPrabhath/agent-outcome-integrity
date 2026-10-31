"""Metric computation over benchmark records.

All metrics are derived from actually-measured runs. Rates that would divide by
zero are reported as ``None`` (== "not applicable / not measured"), never faked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmark.runners import BenchmarkRecord


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@dataclass
class Metrics:
    total_tasks: int
    apparent_success_rate: float | None
    verified_success_rate: float | None
    false_completion_rate: float | None
    outcome_integrity: float | None
    detection_rate: float | None  # of true failures agent-claimed-success, how many caught
    recovery_success_rate: float | None
    mean_recovery_attempts: float | None
    mean_verification_latency_ms: float | None
    # AOIE decision quality vs ground truth:
    aoie_accuracy: float | None
    failure_class_counts: dict[str, int] = field(default_factory=dict)
    outcome_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def compute_metrics(records: list[BenchmarkRecord]) -> Metrics:
    n = len(records)
    apparent = sum(r.agent_claimed_success for r in records)
    verified = sum(r.aoie_outcome == "VERIFIED" for r in records)
    false_completions = sum(r.false_completion for r in records)

    # True failures where the agent nonetheless claimed success (the danger set).
    true_false_claims = [
        r for r in records if r.ground_truth == "failed" and r.agent_claimed_success
    ]
    caught_false_claims = sum(r.caught for r in true_false_claims)

    # Recovery: runs that needed it (not verified on round 0) and eventually verified.
    needed_recovery = [r for r in records if r.recovery_attempts > 0]
    recovered = sum(r.recovered for r in records)

    correct = sum(r.correct for r in records)

    failure_counts: dict[str, int] = {}
    for r in records:
        if r.failure_class:
            failure_counts[r.failure_class] = failure_counts.get(r.failure_class, 0) + 1
    outcome_counts: dict[str, int] = {}
    for r in records:
        outcome_counts[r.aoie_outcome] = outcome_counts.get(r.aoie_outcome, 0) + 1

    total_attempts = sum(r.recovery_attempts for r in records)

    return Metrics(
        total_tasks=n,
        apparent_success_rate=_rate(apparent, n),
        verified_success_rate=_rate(verified, n),
        false_completion_rate=_rate(false_completions, apparent),
        outcome_integrity=_rate(verified, n),
        detection_rate=_rate(caught_false_claims, len(true_false_claims)),
        recovery_success_rate=_rate(recovered, len(needed_recovery)),
        mean_recovery_attempts=round(total_attempts / n, 3) if n else None,
        mean_verification_latency_ms=(
            round(sum(r.verification_latency_ms for r in records) / n, 2) if n else None
        ),
        aoie_accuracy=_rate(correct, n),
        failure_class_counts=failure_counts,
        outcome_counts=outcome_counts,
    )
