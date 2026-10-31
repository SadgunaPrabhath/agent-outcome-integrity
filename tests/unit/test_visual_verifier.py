"""VisualVerifier — perceptual PASS/FAIL and its role as presentational dissent."""

from __future__ import annotations

import pytest

from engine.classification.classifier import OutcomeClassifier
from engine.execution.context import RunContext
from engine.models import (
    AgentClaim,
    MatcherConfig,
    Outcome,
    Postcondition,
    PostconditionType,
    TargetRef,
    TaskSpec,
    VerdictStatus,
    VerifierStatus,
    VerifierType,
)
from engine.observation.inmemory import InMemoryStateSource
from engine.verification.engine import VerificationEngine
from engine.verification.perceptual import average_hash
from engine.verification.visual import VisualVerifier

REF = "ffff0000ffff0000"  # arbitrary 64-bit reference aHash


def _task(expected: object = REF, tolerance: float = 0.0) -> TaskSpec:
    return TaskSpec(
        task_id="visual_001",
        description="Success screen renders",
        target=TargetRef(entity="checkout"),
        expected_postconditions=[
            Postcondition(
                ref="looks_done",
                type=PostconditionType.VISUAL_MATCH,
                entity="checkout",
                expected=expected,
                matcher=MatcherConfig(tolerance=tolerance),
                verification_methods=[VerifierType.VISUAL],
            )
        ],
    )


async def _verify_one(ctx: RunContext):
    report = await VerificationEngine().verify(ctx)
    return report.verdicts[0], report.results


@pytest.mark.asyncio
async def test_matching_screenshot_passes():
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.VISUAL, {"ahash": REF}))
    verdict, results = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.SATISFIED
    assert results[0].confidence == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_different_screenshot_fails():
    ctx = RunContext(task=_task())
    ctx.register_source(
        InMemoryStateSource(VerifierType.VISUAL, {"ahash": "0000ffff0000ffff"})
    )
    verdict, _ = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.VIOLATED


@pytest.mark.asyncio
async def test_hash_computed_from_pixels():
    pixels = [255 if (x + y) % 2 else 0 for y in range(8) for x in range(8)]
    ref = average_hash(pixels, 8, 8)
    ctx = RunContext(task=_task(expected=ref))
    ctx.register_source(
        InMemoryStateSource(VerifierType.VISUAL, {"gray": pixels, "width": 8, "height": 8})
    )
    verdict, _ = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.SATISFIED


@pytest.mark.asyncio
async def test_tolerance_override_allows_near_miss():
    near = "ffff0000ffff0001"  # one bit off from REF
    # Default budget (~10% of 64 = 6 bits) already tolerates this; force a strict
    # budget of 0 to prove the override tightens the check.
    ctx = RunContext(task=_task(tolerance=0.0))
    ctx.register_source(InMemoryStateSource(VerifierType.VISUAL, {"ahash": near}))
    verdict, _ = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.SATISFIED  # within default 6-bit budget

    # A strict budget of 0 differing bits (int(0.5) == 0) rejects the near miss.
    strict = RunContext(task=_task(tolerance=0.5))
    strict.register_source(InMemoryStateSource(VerifierType.VISUAL, {"ahash": near}))
    verdict2, _ = await _verify_one(strict)
    assert verdict2.verdict is VerdictStatus.VIOLATED


@pytest.mark.asyncio
async def test_no_image_is_inconclusive():
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.VISUAL, {}))
    verdict, results = await _verify_one(ctx)
    assert results[0].status is VerifierStatus.INCONCLUSIVE
    assert verdict.verdict is VerdictStatus.UNKNOWN


@pytest.mark.asyncio
async def test_source_error_is_inconclusive():
    ctx = RunContext(task=_task())
    ctx.register_source(
        InMemoryStateSource(VerifierType.VISUAL, {"ahash": REF}, error="capture failed")
    )
    _, results = await _verify_one(ctx)
    assert results[0].status is VerifierStatus.INCONCLUSIVE


@pytest.mark.asyncio
async def test_visual_optimism_caught_by_backend_at_task_level():
    """Screenshot says success (VISUAL SATISFIED), backend says the state never
    changed (FIELD VIOLATED). These are necessarily distinct postconditions, so
    the false completion surfaces at the task level: the run is not VERIFIED and
    ``false_completion`` is flagged, even though the per-check backend failure is
    classified on its own terms (WRONG_VALUE here)."""
    task = _task()
    task.expected_postconditions.append(
        Postcondition(
            ref="persisted",
            type=PostconditionType.FIELD_EQUALS,
            entity="checkout",
            field="status",
            expected="paid",
            verification_methods=[VerifierType.API],
        )
    )
    ctx = RunContext(task=task)
    ctx.register_source(InMemoryStateSource(VerifierType.VISUAL, {"ahash": REF}))
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"status": "pending"}))

    report = await VerificationEngine().verify(ctx)
    visual_verdict = next(v for v in report.verdicts if v.postcondition_ref == "looks_done")
    outcome = OutcomeClassifier().classify(
        report.verdicts, ctx.task, AgentClaim(claimed_success=True)
    )
    assert visual_verdict.verdict is VerdictStatus.SATISFIED  # the screen looked done
    assert outcome.outcome is not Outcome.VERIFIED  # but the backend disagreed
    assert outcome.false_completion is True


def test_verifier_only_handles_visual_match():
    v = VisualVerifier(InMemoryStateSource(VerifierType.VISUAL, {}))
    visual_pc = Postcondition(
        ref="v", type=PostconditionType.VISUAL_MATCH, entity="x", expected=REF
    )
    field_pc = Postcondition(
        ref="f", type=PostconditionType.FIELD_EQUALS, entity="x", field="n", expected="y"
    )
    assert v.can_verify(visual_pc) is True
    assert v.can_verify(field_pc) is False


def test_visual_match_requires_reference_hash():
    with pytest.raises(ValueError):
        Postcondition(
            ref="v", type=PostconditionType.VISUAL_MATCH, entity="x", expected=None
        )
