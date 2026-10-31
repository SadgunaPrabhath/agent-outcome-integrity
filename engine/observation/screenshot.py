"""ScreenshotStateSource — turns a captured screenshot into a VISUAL observation.

This is the bridge between the browser adapter (which can grab a PNG screenshot
of the page) and the Visual verifier (which judges a ``VISUAL_MATCH``
postcondition against a reference aHash). The source captures PNG bytes from any
async ``capture`` callable — a Playwright page's ``screenshot()``, or a fixed
image in tests — decodes them to grayscale with the dependency-free PNG codec,
computes the aHash, and returns it in the observation state.

Like every StateSource it never raises for an ordinary failure: an empty or
undecodable capture yields an ``Observation`` with ``error`` set, so the Visual
verifier degrades to INCONCLUSIVE instead of crashing verification.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from engine.execution.context import StateSource
from engine.models import Observation, Postcondition, TargetRef, VerifierType
from engine.verification.perceptual import average_hash
from engine.verification.png import decode_png_gray

CaptureFn = Callable[[], Awaitable[bytes]]


class ScreenshotStateSource(StateSource):
    verifier_type = VerifierType.VISUAL

    def __init__(
        self,
        capture: CaptureFn,
        *,
        source_name: str = "screenshot",
        screenshot_path: str | None = None,
    ) -> None:
        self._capture = capture
        self._source_name = source_name
        self._screenshot_path = screenshot_path

    @classmethod
    def from_driver(cls, driver: object, **kwargs: object) -> ScreenshotStateSource:
        """Build a source that screenshots a PageDriver (Playwright or simulator)."""
        async def capture() -> bytes:
            return await driver.screenshot()  # type: ignore[attr-defined]

        return cls(capture, source_name="screenshot:page", **kwargs)  # type: ignore[arg-type]

    async def read(self, pc: Postcondition, target: TargetRef) -> Observation:
        try:
            png = await self._capture()
        except Exception as exc:  # noqa: BLE001 - capture failure must not crash verification
            return self._error(f"capture failed: {exc}")
        if not png:
            return self._error("empty screenshot")
        try:
            gray, width, height = decode_png_gray(png)
        except Exception as exc:  # noqa: BLE001 - PngError/zlib/struct all degrade gracefully
            return self._error(f"undecodable screenshot: {exc}")

        state: dict[str, object] = {
            "ahash": average_hash(gray, width, height),
            "width": width,
            "height": height,
        }
        if self._screenshot_path:
            state["screenshot_path"] = self._screenshot_path
        return Observation(
            observer_type=self.verifier_type, source=self._source_name, state=state
        )

    def _error(self, message: str) -> Observation:
        return Observation(
            observer_type=self.verifier_type, source=self._source_name, error=message
        )
