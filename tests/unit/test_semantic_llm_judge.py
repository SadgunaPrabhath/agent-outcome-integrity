"""AnthropicSemanticJudge logic + async-judge plumbing (no network)."""

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
from engine.verification.llm_judge import AnthropicSemanticJudge, _to_judgment
from engine.verification.semantic import Judgment

# --- fake Anthropic client (structured tool output) --------------------------


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, verdict, confidence, rationale="ok", raises=False):
        self._verdict, self._confidence, self._rationale = verdict, confidence, rationale
        self._raises = raises

    async def create(self, **kwargs):
        if self._raises:
            raise RuntimeError("network down")
        return _Resp(
            [
                _Block(type="text", text="deciding"),
                _Block(
                    type="tool_use",
                    name="report_judgment",
                    input={
                        "verdict": self._verdict,
                        "confidence": self._confidence,
                        "rationale": self._rationale,
                    },
                ),
            ]
        )


class _FakeClient:
    def __init__(self, messages):
        self.messages = messages


def _judge_with(verdict, confidence, **kw):
    j = AnthropicSemanticJudge()
    j._client = _FakeClient(_FakeMessages(verdict, confidence, **kw))
    return j


# --- _to_judgment mapping ----------------------------------------------------


def test_verdict_mapping_and_confidence_clamp():
    assert _to_judgment({"verdict": "PASS", "confidence": 0.9, "rationale": "x"}, "n").status is (
        VerifierStatus.PASS
    )
    assert _to_judgment({"verdict": "fail", "confidence": 2.0}, "n").status is VerifierStatus.FAIL
    # Out-of-range confidence is clamped; unknown verdict -> INCONCLUSIVE.
    assert _to_judgment({"verdict": "PASS", "confidence": 2.0}, "n").confidence == 1.0
    assert _to_judgment({"verdict": "???", "confidence": "bad"}, "n").status is (
        VerifierStatus.INCONCLUSIVE
    )
    assert _to_judgment({"verdict": "PASS", "confidence": "bad"}, "n").confidence == 0.0


# --- the judge with a fake client -------------------------------------------


@pytest.mark.asyncio
async def test_judge_returns_structured_pass():
    out = await _judge_with("PASS", 0.95).judge("refund processed", "The refund went through.", {})
    assert out.status is VerifierStatus.PASS
    assert out.confidence == 0.95
    assert out.judge.startswith("anthropic:")


@pytest.mark.asyncio
async def test_judge_degrades_to_inconclusive_on_api_error():
    out = await _judge_with("PASS", 0.9, raises=True).judge("x", "y", {})
    assert out.status is VerifierStatus.INCONCLUSIVE
    assert "unavailable" in out.rationale


@pytest.mark.asyncio
async def test_judge_inconclusive_when_no_tool_block():
    j = AnthropicSemanticJudge()

    class _NoTool:
        async def create(self, **kwargs):
            return _Resp([_Block(type="text", text="I think so")])

    j._client = _FakeClient(_NoTool())
    out = await j.judge("x", "y", {})
    assert out.status is VerifierStatus.INCONCLUSIVE


# --- async judge plumbing through the verifier ------------------------------


def _semantic_task(expected: str) -> TaskSpec:
    return TaskSpec(
        task_id="s", description="summary confirms refund",
        target=TargetRef(entity="ticket"),
        expected_postconditions=[
            Postcondition(ref="mentions", type=PostconditionType.SEMANTIC,
                          entity="ticket", expected=expected,
                          verification_methods=[VerifierType.SEMANTIC])
        ],
    )


@pytest.mark.asyncio
async def test_async_judge_integrates_and_is_capped():
    """An async LLM judge plugs into VerificationEngine and its confidence is
    still capped at the SEMANTIC tier ceiling (0.4)."""

    class AsyncPassJudge:
        name = "async-stub"

        async def judge(self, expected, observed, context):
            return Judgment(VerifierStatus.PASS, 0.99, "async says yes", self.name)

    engine = VerificationEngine(judge=AsyncPassJudge())
    ctx = RunContext(task=_semantic_task("refund processed"))
    ctx.register_source(InMemoryStateSource(VerifierType.SEMANTIC, {"text": "refund processed"}))
    report = await engine.verify(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.SATISFIED
    assert report.results[0].confidence <= 0.4
    assert report.evidence[0].comparison["judge"] == "async-stub"


@pytest.mark.asyncio
async def test_sync_heuristic_judge_still_works():
    """Regression: the default sync judge path is unchanged by async support."""
    engine = VerificationEngine()  # default HeuristicSemanticJudge
    ctx = RunContext(task=_semantic_task("refund processed"))
    ctx.register_source(
        InMemoryStateSource(VerifierType.SEMANTIC, {"text": "The refund was processed."})
    )
    report = await engine.verify(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.SATISFIED
