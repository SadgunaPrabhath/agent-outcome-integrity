"""PageDriver — the thin surface a browser agent needs, with two backends.

The ``BrowserUiAdapter`` is written against :class:`PageDriver` (goto / fill /
click / read text / screenshot) so its logic — plan the mutation, type it, submit
it, and form a claim from *what the page shows* — is independent of how the page
is actually driven. Two backends implement it:

  * :class:`PlaywrightPageDriver` — the real thing: a Chromium page. Requires the
    optional ``browser`` extra (``pip install -e ".[browser]"`` +
    ``playwright install chromium``). Imported lazily so the package stays
    importable without Playwright.

  * :class:`HttpxPageDriver` — a browser-free page *simulator* that faithfully
    reimplements the demo page's script (fetch the mutation, set the optimistic
    status banner from the HTTP status) over httpx. It exists so the adapter can
    be exercised end-to-end against the real demo app in CI — no browser binary,
    no skipped tests — while behaving exactly as the browser agent would,
    including confidently reporting "Saved ✓" on an optimistic 200.

Both drive the page served by ``environments/demo_app/ui.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

import httpx


@dataclass
class NetworkRecord:
    """One network response the page observed, for the execution trace."""

    method: str
    url: str
    status: int
    body: str = ""


@runtime_checkable
class PageDriver(Protocol):
    """Minimal page automation surface used by :class:`BrowserUiAdapter`."""

    async def goto(self, url: str) -> None: ...
    async def fill(self, selector: str, value: str) -> None: ...
    async def click(self, selector: str) -> None: ...
    async def text_content(self, selector: str) -> str | None: ...
    async def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> None: ...
    async def screenshot(self) -> bytes: ...
    def network_events(self) -> list[NetworkRecord]: ...
    async def close(self) -> None: ...


# Selectors are shared so the adapter and both drivers agree on the page shape.
SEL_FIELD = "#field"
SEL_VALUE = "#value"
SEL_SAVE = "#save"
SEL_STATUS = "#status"
SEL_RESULT = "#result"
SEL_CURRENT = "#current"


class HttpxPageDriver:
    """Browser-free page simulator that drives the real demo app over HTTP.

    It mirrors the page's JavaScript: ``#save`` issues the same ``PUT`` the
    browser would, and the ``#status`` banner is set optimistically from the HTTP
    status. This is a faithful stand-in for CI, not a mock of the app — the app's
    real scenario logic runs unchanged.
    """

    def __init__(
        self, base_url: str = "http://testserver", *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._inputs: dict[str, str] = {}
        self._dom: dict[str, str] = {}
        self._network: list[NetworkRecord] = []
        self._collection = ""
        self._record_id = ""

    async def _request(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, path, json=json)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as c:
            return await c.request(method, path, json=json)

    async def goto(self, url: str) -> None:
        # Parse /app/{collection}/{record_id} to learn the target, like the page's
        # inline script does from window.location.
        parts = [p for p in urlsplit(url).path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "app":
            self._collection, self._record_id = parts[1], parts[2]
        self._dom = {}
        self._inputs = {SEL_FIELD: "name", SEL_VALUE: ""}
        await self._refresh_current()

    async def fill(self, selector: str, value: str) -> None:
        self._inputs[selector] = value

    async def click(self, selector: str) -> None:
        if selector != SEL_SAVE:
            return
        field_name = self._inputs.get(SEL_FIELD, "name")
        value = self._inputs.get(SEL_VALUE, "")
        path = f"/api/{self._collection}/{self._record_id}"
        try:
            resp = await self._request("PUT", path, json={"fields": {field_name: value}})
        except httpx.HTTPError as exc:  # network-level failure the page would surface
            self._dom[SEL_STATUS] = f"Error ✗ ({exc})"
            self._network.append(NetworkRecord("PUT", path, 0, str(exc)))
            return
        self._network.append(NetworkRecord("PUT", path, resp.status_code, resp.text[:500]))
        self._dom[SEL_RESULT] = resp.text[:500]
        # Optimistic banner: 2xx alone means "Saved ✓" (the false-completion surface).
        self._dom[SEL_STATUS] = (
            "Saved ✓" if resp.is_success else f"Error ✗ ({resp.status_code})"
        )
        await self._refresh_current()

    async def _refresh_current(self) -> None:
        try:
            resp = await self._request("GET", f"/ui/{self._collection}/{self._record_id}")
            self._dom[SEL_CURRENT] = resp.text[:500] if resp.is_success else f"({resp.status_code})"
        except httpx.HTTPError:
            self._dom[SEL_CURRENT] = "(error)"

    async def text_content(self, selector: str) -> str | None:
        return self._dom.get(selector)

    async def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> None:
        return None

    async def screenshot(self) -> bytes:
        # No real raster without a browser; return the status text as bytes so the
        # trace has a non-empty, deterministic artifact stand-in.
        return self._dom.get(SEL_STATUS, "").encode("utf-8")

    def network_events(self) -> list[NetworkRecord]:
        return list(self._network)

    async def close(self) -> None:
        return None


class PlaywrightPageDriver:
    """Real Chromium-backed :class:`PageDriver` (optional ``browser`` extra)."""

    def __init__(self, base_url: str = "http://localhost:8137", *, headless: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None
        self._network: list[NetworkRecord] = []

    async def launch(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise RuntimeError(
                "Playwright is not installed. Install with: "
                'pip install -e ".[browser]" && playwright install chromium'
            ) from exc
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        self._page.on("response", self._on_response)

    def _on_response(self, response: object) -> None:  # pragma: no cover - needs a browser
        req = response.request  # type: ignore[attr-defined]
        self._network.append(
            NetworkRecord(
                method=req.method,
                url=response.url,  # type: ignore[attr-defined]
                status=response.status,  # type: ignore[attr-defined]
            )
        )

    def _require_page(self) -> object:
        if self._page is None:
            raise RuntimeError("PlaywrightPageDriver.launch() was not called")
        return self._page

    async def goto(self, url: str) -> None:  # pragma: no cover - needs a browser
        target = url if url.startswith("http") else f"{self.base_url}{url}"
        await self._require_page().goto(target)  # type: ignore[attr-defined]

    async def fill(self, selector: str, value: str) -> None:  # pragma: no cover
        await self._require_page().fill(selector, value)  # type: ignore[attr-defined]

    async def click(self, selector: str) -> None:  # pragma: no cover
        await self._require_page().click(selector)  # type: ignore[attr-defined]

    async def text_content(self, selector: str) -> str | None:  # pragma: no cover
        return await self._require_page().text_content(selector)  # type: ignore[attr-defined]

    async def wait_for_selector(
        self, selector: str, timeout_ms: int = 5000
    ) -> None:  # pragma: no cover
        await self._require_page().wait_for_selector(  # type: ignore[attr-defined]
            selector, timeout=timeout_ms
        )

    async def screenshot(self) -> bytes:  # pragma: no cover - needs a browser
        return await self._require_page().screenshot()  # type: ignore[attr-defined]

    def network_events(self) -> list[NetworkRecord]:
        return list(self._network)

    async def close(self) -> None:  # pragma: no cover - needs a browser
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
