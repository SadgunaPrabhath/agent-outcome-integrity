"""HttpStateSource — observe state by reading an HTTP endpoint.

Used for both the authoritative API read-back (``/api/...``) and the
presentational DOM/UI view (``/ui/...``); the two differ only in ``verifier_type``
and the path template. The path template is formatted with the target's locator
plus a few standard keys, so a single class serves every entity.
"""

from __future__ import annotations

from typing import Any

import httpx

from engine.execution.context import StateSource
from engine.models import Observation, Postcondition, PostconditionType, TargetRef, VerifierType


class HttpStateSource(StateSource):
    def __init__(
        self,
        verifier_type: VerifierType,
        base_url: str,
        path_template: str,
        *,
        timeout_s: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.verifier_type = verifier_type
        self.base_url = base_url.rstrip("/")
        self.path_template = path_template
        self.timeout_s = timeout_s
        self._client = client  # if provided (e.g. ASGI test transport), reused

    def _params(self, target: TargetRef) -> dict[str, Any]:
        return {"entity": target.entity, "entity_id": target.entity_id, **target.locator}

    async def read(self, pc: Postcondition, target: TargetRef) -> Observation:
        path = self.path_template.format(**self._params(target))
        src = f"GET {self.base_url}{path}"
        try:
            resp = await self._get(path)
        except Exception as exc:  # noqa: BLE001 - any transport error -> inconclusive observation
            return Observation(
                observer_type=self.verifier_type, source=src, error=str(exc)
            )

        if resp.status_code == 404:
            return Observation(
                observer_type=self.verifier_type, source=src, state={"exists": False}
            )
        if resp.status_code >= 400:
            return Observation(
                observer_type=self.verifier_type,
                source=src,
                error=f"HTTP {resp.status_code}",
            )

        data = resp.json()
        state: dict[str, Any] = dict(data) if isinstance(data, dict) else {"value": data}
        state.setdefault("exists", True)
        if pc.type is PostconditionType.COUNT_EQUALS and "count" not in state:
            # A record read cannot answer a count; leave it inconclusive.
            state.pop("exists", None)
        return Observation(observer_type=self.verifier_type, source=src, state=state)

    async def _get(self, path: str) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(path)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s) as c:
            return await c.get(path)
