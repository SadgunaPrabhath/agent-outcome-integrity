"""SemanticVerifier — keyless heuristic judge, tier caps, and pluggability."""

from __future__ import annotations

import pytest

from engine.execution.context import RunContext
from engine.models import (
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
from engine.verification.semantic import (
    HeuristicSemanticJudge,
    Judgment,
    SemanticVerifier,
)


def _task(expected: str) -> TaskSpec:
    return TaskSpec(
        task_id="semantic_001",
        description="Summary confirms the refund",
        target=TargetRef(entity="ticket"),
        expected_postconditions=[
            Postcondition(
                ref="mentions_refund",
                type=PostconditionType.SEMANTIC,
                entity="ticket",
                expected=expected,
                verification_methods=[VerifierType.SEMANTIC],
            )
        ],
    )


async def _verify_one(ctx: RunContext):
    report = await VerificationEngine().verify(ctx)
    return report.verdicts[0], report.results[0]


# --- the heuristic judge in isolation ---------------------------------------


def test_judge_passes_when_terms_present():
    j = HeuristicSemanticJudge()
    out = j.judge("refund processed", "The refund was processed successfully.", {})
    assert out.status is VerifierStatus.PASS
    assert 0.0 < out.confidence <= 1.0


def test_judge_fails_on_negation():
    j = HeuristicSemanticJudge()
    out = j.judge("refund processed", "The refund was not processed.", {})
    assert out.status is VerifierStatus.FAIL


def test_judge_inconclusive_when_unaddressed():
    j = HeuristicSemanticJudge()
    out = j.judge("refund processed", "Your ticket has been assigned to an agent.", {})
    assert out.status is VerifierStatus.INCONCLUSIVE


def test_judge_names_itself_a_heuristic():
    assert HeuristicSemanticJudge().name == "heuristic-lexical"


# --- verifier through the engine --------------------------------------------


@pytest.mark.asyncio
async def test_semantic_pass_is_capped_at_tier():
    ctx = RunContext(task=_task("refund processed"))
    ctx.register_source(
        InMemoryStateSource(
            VerifierType.SEMANTIC, {"text": "Refund processed and the amount was returned."}
        )
    )
    verdict, result = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.SATISFIED
    assert result.confidence <= 0.4  # SEMANTIC tier ceiling


@pytest.mark.asyncio
async def test_semantic_fail_on_contradiction():
    ctx = RunContext(task=_task("refund processed"))
    ctx.register_source(
        InMemoryStateSource(VerifierType.SEMANTIC, {"text": "The refund was never processed."})
    )
    verdict, _ = await _verify_one(ctx)
    assert verdict.verdict is VerdictStatus.VIOLATED


@pytest.mark.asyncio
async def test_semantic_unknown_when_text_silent():
    ctx = RunContext(task=_task("refund processed"))
    ctx.register_source(
        InMemoryStateSource(VerifierType.SEMANTIC, {"text": "Ticket assigned to support."})
    )
    verdict, result = await _verify_one(ctx)
    assert result.status is VerifierStatus.INCONCLUSIVE
    assert verdict.verdict is VerdictStatus.UNKNOWN


@pytest.mark.asyncio
async def test_semantic_yields_to_authoritative_backend():
    """Prose says done, backend says otherwise -> backend decides VIOLATED."""
    task = _task("name updated to alice")
    task.expected_postconditions.append(
        Postcondition(
            ref="name",
            type=PostconditionType.FIELD_EQUALS,
            entity="ticket",
            field="name",
            expected="Alice",
            verification_methods=[VerifierType.API],
        )
    )
    ctx = RunContext(task=task)
    ctx.register_source(
        InMemoryStateSource(VerifierType.SEMANTIC, {"text": "The name was updated to Alice."})
    )
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Bob"}))
    report = await VerificationEngine().verify(ctx)
    backend_verdict = next(v for v in report.verdicts if v.postcondition_ref == "name")
    assert backend_verdict.verdict is VerdictStatus.VIOLATED


@pytest.mark.asyncio
async def test_custom_judge_is_pluggable():
    class AlwaysPass:
        name = "stub-judge"

        def judge(self, expected, observed, context):
            return Judgment(VerifierStatus.PASS, 0.99, "stubbed", self.name)

    engine = VerificationEngine(judge=AlwaysPass())
    ctx = RunContext(task=_task("anything at all"))
    ctx.register_source(InMemoryStateSource(VerifierType.SEMANTIC, {"text": "unrelated"}))
    report = await engine.verify(ctx)
    result = report.results[0]
    assert result.status is VerifierStatus.PASS
    # Even a 0.99-confident judge is capped at the SEMANTIC tier.
    assert result.confidence <= 0.4
    assert report.evidence[0].comparison["judge"] == "stub-judge"


def test_verifier_only_handles_semantic():
    v = SemanticVerifier(InMemoryStateSource(VerifierType.SEMANTIC, {}))
    sem = Postcondition(
        ref="s", type=PostconditionType.SEMANTIC, entity="x", expected="done"
    )
    field = Postcondition(
        ref="f", type=PostconditionType.FIELD_EQUALS, entity="x", field="n", expected="y"
    )
    assert v.can_verify(sem) is True
    assert v.can_verify(field) is False
