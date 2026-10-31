"""AnthropicSemanticJudge — a real LLM backend for the SEMANTIC tier.

The default semantic judge is a labelled lexical heuristic. This is the pluggable
real-model alternative: it asks Claude whether the observed text satisfies a prose
expectation and returns a structured :class:`Judgment`. It implements the same
:class:`SemanticJudge` protocol, so it drops into ``VerificationEngine(judge=...)``
with nothing else changed.

Two disciplines carry over from the rest of AOIE:

  * **Last resort, capped confidence.** SEMANTIC is the lowest tier (0.4 ceiling),
    non-authoritative and non-deterministic. The reconciler never lets it outrank
    a backend read, and ``SemanticVerifier`` caps whatever confidence the model
    reports. A confident LLM can never masquerade as ground truth.
  * **Conservative and honest on failure.** The model is instructed to PASS only
    when the condition is clearly satisfied, FAIL when clearly contradicted, and
    INCONCLUSIVE when the text does not address it. If the API is unavailable or
    returns nothing usable, the judge degrades to INCONCLUSIVE — it never invents
    a verdict.

``anthropic`` is imported lazily, so importing this module never requires the
SDK. Install with ``pip install -e ".[llm]"`` and provide credentials.
"""

from __future__ import annotations

from typing import Any

from engine.models import VerifierStatus
from engine.verification.semantic import Judgment

_SYSTEM = (
    "You are a strict outcome-verification judge. You are given an EXPECTED "
    "condition (in prose) and the OBSERVED text produced by a system. Decide "
    "whether the observed text satisfies the expected condition. Be conservative: "
    "answer PASS only if it is clearly satisfied, FAIL if it is clearly "
    "contradicted, and INCONCLUSIVE if the text does not address the condition or "
    "is ambiguous. Report your decision by calling the report_judgment tool."
)

_TOOL: dict[str, Any] = {
    "name": "report_judgment",
    "description": "Report the verification decision.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL", "INCONCLUSIVE"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string"},
        },
        "required": ["verdict", "confidence", "rationale"],
    },
}

_VERDICTS = {
    "PASS": VerifierStatus.PASS,
    "FAIL": VerifierStatus.FAIL,
    "INCONCLUSIVE": VerifierStatus.INCONCLUSIVE,
}


class AnthropicSemanticJudge:
    """SEMANTIC judge backed by Claude (Messages API, structured tool output)."""

    def __init__(self, model: str = "claude-opus-5", *, max_tokens: int = 1024) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"anthropic:{model}"
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - only without the extra
                raise RuntimeError(
                    'anthropic SDK not installed. Install with: pip install -e ".[llm]"'
                ) from exc
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def judge(self, expected: str, observed: str, context: dict[str, Any]) -> Judgment:
        try:
            client = self._ensure_client()
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_SYSTEM,
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "report_judgment"},
                messages=[{"role": "user", "content": _prompt(expected, observed)}],
            )
        except Exception as exc:  # noqa: BLE001 - any API failure degrades gracefully
            return Judgment(VerifierStatus.INCONCLUSIVE, 0.0, f"llm judge unavailable: {exc}", self.name)

        for block in response.content:
            if block.type == "tool_use" and block.name == "report_judgment":
                return _to_judgment(dict(block.input), self.name)
        return Judgment(
            VerifierStatus.INCONCLUSIVE, 0.0, "no structured judgment returned", self.name
        )


def _prompt(expected: str, observed: str) -> str:
    return f"EXPECTED condition:\n{expected}\n\nOBSERVED text:\n{observed}"


def _to_judgment(data: dict[str, Any], name: str) -> Judgment:
    status = _VERDICTS.get(str(data.get("verdict", "")).upper(), VerifierStatus.INCONCLUSIVE)
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    rationale = str(data.get("rationale", ""))
    return Judgment(status, confidence, rationale, name)
