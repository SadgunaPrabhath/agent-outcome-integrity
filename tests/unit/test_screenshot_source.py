"""ScreenshotStateSource — capture -> decode -> aHash, feeding the Visual verifier."""

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
from engine.observation.screenshot import ScreenshotStateSource
from engine.verification.engine import VerificationEngine
from engine.verification.perceptual import average_hash
from engine.verification.png import encode_png


def _checker(w: int = 16, h: int = 16) -> tuple[list[int], bytes]:
    gray = [255 if (x + y) % 2 == 0 else 0 for y in range(h) for x in range(w)]
    return gray, encode_png(gray, w, h, channels=1)


def _capture_of(png: bytes):
    async def capture() -> bytes:
        return png

    return capture


def _visual_task(reference: str) -> TaskSpec:
    return TaskSpec(
        task_id="visual_shot",
        description="page looks like the reference",
        target=TargetRef(entity="page"),
        expected_postconditions=[
            Postcondition(
                ref="looks_right", type=PostconditionType.VISUAL_MATCH,
                entity="page", expected=reference,
                verification_methods=[VerifierType.VISUAL],
            )
        ],
    )


@pytest.mark.asyncio
async def test_read_produces_ahash_of_decoded_image():
    gray, png = _checker()
    src = ScreenshotStateSource(_capture_of(png))
    obs = await src.read(_visual_task("x").expected_postconditions[0], TargetRef(entity="page"))
    assert obs.ok
    assert obs.state["ahash"] == average_hash(gray, 16, 16)
    assert (obs.state["width"], obs.state["height"]) == (16, 16)


@pytest.mark.asyncio
async def test_visual_verify_passes_on_matching_screenshot():
    gray, png = _checker()
    reference = average_hash(gray, 16, 16)
    ctx = RunContext(task=_visual_task(reference))
    ctx.register_source(ScreenshotStateSource(_capture_of(png)))
    report = await VerificationEngine().verify(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.SATISFIED


@pytest.mark.asyncio
async def test_visual_verify_fails_on_different_screenshot():
    # A solid image hashes to all-ones ('f'*16); reference all-zeros is maximally
    # far (Hamming 64), so the perceptual check must VIOLATE.
    solid = [128] * (16 * 16)
    png = encode_png(solid, 16, 16, channels=1)
    ctx = RunContext(task=_visual_task("0" * 16))
    ctx.register_source(ScreenshotStateSource(_capture_of(png)))
    report = await VerificationEngine().verify(ctx)
    assert report.verdicts[0].verdict is VerdictStatus.VIOLATED


@pytest.mark.asyncio
async def test_empty_capture_is_inconclusive():
    ctx = RunContext(task=_visual_task("f" * 16))
    ctx.register_source(ScreenshotStateSource(_capture_of(b"")))
    report = await VerificationEngine().verify(ctx)
    assert report.results[0].status is VerifierStatus.INCONCLUSIVE


@pytest.mark.asyncio
async def test_undecodable_capture_is_graceful():
    src = ScreenshotStateSource(_capture_of(b"\x89PNG\r\n\x1a\n garbage"))
    obs = await src.read(_visual_task("x").expected_postconditions[0], TargetRef(entity="page"))
    assert not obs.ok
    assert "undecodable" in (obs.error or "")


@pytest.mark.asyncio
async def test_capture_exception_does_not_crash():
    async def boom() -> bytes:
        raise RuntimeError("browser died")

    src = ScreenshotStateSource(boom)
    obs = await src.read(_visual_task("x").expected_postconditions[0], TargetRef(entity="page"))
    assert not obs.ok
    assert "capture failed" in (obs.error or "")


@pytest.mark.asyncio
async def test_from_driver_screenshots_a_pagedriver():
    _, png = _checker()

    class StubDriver:
        async def screenshot(self) -> bytes:
            return png

    src = ScreenshotStateSource.from_driver(StubDriver())
    obs = await src.read(_visual_task("x").expected_postconditions[0], TargetRef(entity="page"))
    assert obs.ok
    assert "ahash" in obs.state
