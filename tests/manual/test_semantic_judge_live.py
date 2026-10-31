"""Opt-in live proof: the real Claude semantic judge on clear-cut cases.

Deselected by default (marked ``live``). To run:

    pip install -e ".[dev,llm]"
    export ANTHROPIC_API_KEY=...        # or: ant auth login
    pytest -m live -k semantic_judge

The judge is the lowest, last-resort tier, so this asserts only the two
unambiguous directions a competent model must get right: a clearly-satisfied
condition PASSes and a clearly-contradicted one FAILs. Confidence remains capped
at the SEMANTIC tier by the verifier regardless.
"""

from __future__ import annotations

import pytest

from engine.models import VerifierStatus
from engine.verification.llm_judge import AnthropicSemanticJudge

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_judge_passes_clear_satisfaction():
    judge = AnthropicSemanticJudge()
    out = await judge.judge(
        "the refund was processed",
        "We have processed your refund of $40 back to your card.",
        {},
    )
    assert out.status is VerifierStatus.PASS


@pytest.mark.asyncio
async def test_live_judge_fails_clear_contradiction():
    judge = AnthropicSemanticJudge()
    out = await judge.judge(
        "the refund was processed",
        "We were unable to process your refund; no money has been returned.",
        {},
    )
    assert out.status is VerifierStatus.FAIL
