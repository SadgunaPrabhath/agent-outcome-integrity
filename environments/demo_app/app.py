"""Controlled demo application with deterministic failure injection.

This is the environment AOIE verifies against. It exposes three views of state
that can be made to diverge on demand:

  * ``GET /api/{collection}/{id}``  authoritative read (backed by SQLite)   -> API source
  * ``GET /ui/{collection}/{id}``   optimistic "what the UI shows" view      -> DOM source
  * the SQLite file itself          ground truth                              -> DB source

Mutations (``PUT``/``POST``/``DELETE``) behave according to the *scenario* set
for the target via ``/admin/scenario``. A naive agent only ever sees the 200 OK
and the optimistic UI, which is exactly how false completions arise.

Nothing here persists secrets; accounts are synthetic.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from environments.demo_app.scenarios import Scenario
from environments.demo_app.store import RecordStore
from environments.demo_app.ui import render_page


class SeedBody(BaseModel):
    collection: str
    record_id: str
    fields: dict[str, Any]


class ScenarioBody(BaseModel):
    collection: str
    record_id: str
    scenario: Scenario


class MutationBody(BaseModel):
    fields: dict[str, Any]


def _key(collection: str, record_id: str) -> str:
    return f"{collection}/{record_id}"


def create_app(db_path: str | None = None, timeout_delay_s: float = 3.0) -> FastAPI:
    db_path = db_path or os.environ.get("AOIE_DEMO_DB", "demo_app.sqlite")
    store = RecordStore(db_path)
    app = FastAPI(title="AOIE Demo App", version="0.1.0")

    # Per-target scenario, optimistic UI cache, and stale-read cache. Held in
    # process memory: the demo runs single-process for reproducible benchmarks.
    app.state.store = store
    app.state.db_path = db_path
    app.state.scenarios: dict[str, Scenario] = {}
    app.state.ui_cache: dict[str, dict[str, Any]] = {}
    app.state.stale_cache: dict[str, dict[str, Any]] = {}
    app.state.attempts: dict[str, int] = {}  # mutation counts (for transient faults)

    def scenario_for(collection: str, record_id: str) -> Scenario:
        return app.state.scenarios.get(_key(collection, record_id), Scenario.NONE)

    # --- admin (test/benchmark control plane) --------------------------------
    @app.post("/admin/reset")
    def admin_reset() -> dict[str, str]:
        store.reset()
        app.state.scenarios.clear()
        app.state.ui_cache.clear()
        app.state.stale_cache.clear()
        app.state.attempts.clear()
        return {"status": "reset"}

    @app.post("/admin/seed")
    def admin_seed(body: SeedBody) -> dict[str, Any]:
        store.seed(body.collection, body.record_id, body.fields)
        app.state.ui_cache.pop(_key(body.collection, body.record_id), None)
        app.state.stale_cache.pop(_key(body.collection, body.record_id), None)
        return {"status": "seeded", "fields": body.fields}

    @app.post("/admin/scenario")
    def admin_scenario(body: ScenarioBody) -> dict[str, str]:
        app.state.scenarios[_key(body.collection, body.record_id)] = body.scenario
        return {"status": "scenario_set", "scenario": body.scenario.value}

    # --- reads ----------------------------------------------------------------
    @app.get("/api/{collection}/{record_id}")
    def api_read(collection: str, record_id: str) -> dict[str, Any]:
        key = _key(collection, record_id)
        if key in app.state.stale_cache:  # authoritative read is stale
            return app.state.stale_cache[key]
        record = store.get(collection, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not found")
        return record

    @app.get("/app/{collection}/{record_id}", response_class=HTMLResponse)
    def ui_page(collection: str, record_id: str, field: str = "name") -> str:
        """Serve the HTML form a browser agent drives (see ui.render_page)."""
        return render_page(collection, record_id, default_field=field)

    @app.get("/ui/{collection}/{record_id}")
    def ui_read(collection: str, record_id: str) -> dict[str, Any]:
        key = _key(collection, record_id)
        if key in app.state.ui_cache:  # optimistic view
            return app.state.ui_cache[key]
        record = store.get(collection, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="not found")
        return record

    # --- mutation -------------------------------------------------------------
    @app.put("/api/{collection}/{record_id}")
    def api_update(
        collection: str, record_id: str, body: MutationBody, response: Response
    ) -> dict[str, Any]:
        return _mutate(collection, record_id, body.fields, response)

    @app.post("/api/{collection}")
    def api_create(collection: str, body: SeedBody, response: Response) -> dict[str, Any]:
        return _mutate(collection, body.record_id, body.fields, response, creating=True)

    @app.delete("/api/{collection}/{record_id}")
    def api_delete(collection: str, record_id: str, response: Response) -> dict[str, Any]:
        scenario = scenario_for(collection, record_id)
        key = _key(collection, record_id)
        if scenario is Scenario.AUTH_FAILURE:
            raise HTTPException(status_code=401, detail="unauthorized")
        if scenario is Scenario.TIMEOUT:
            time.sleep(min(timeout_delay_s, 0.2))
            raise HTTPException(status_code=504, detail="gateway timeout")
        if scenario is Scenario.FAIL_BACKEND_WRITE:
            # UI reflects deletion, backend keeps the record.
            app.state.ui_cache[key] = {"exists": False}
            return {"deleted": True}  # optimistic lie
        store.delete(collection, record_id)
        app.state.ui_cache[key] = {"exists": False}
        return {"deleted": True}

    def _mutate(
        collection: str,
        record_id: str,
        fields: dict[str, Any],
        response: Response,
        creating: bool = False,
    ) -> dict[str, Any]:
        scenario = scenario_for(collection, record_id)
        key = _key(collection, record_id)

        if scenario is Scenario.AUTH_FAILURE:
            raise HTTPException(status_code=401, detail="unauthorized")

        if scenario is Scenario.TIMEOUT:
            # Stall briefly, then fail with a gateway timeout WITHOUT persisting.
            # (Deterministic across in-process and networked deployments.)
            time.sleep(min(timeout_delay_s, 0.2))
            raise HTTPException(status_code=504, detail="gateway timeout")

        optimistic = dict(store.get(collection, record_id) or {})
        optimistic.update(fields)
        app.state.ui_cache[key] = optimistic  # UI always shows success

        app.state.attempts[key] = app.state.attempts.get(key, 0) + 1

        if scenario is Scenario.FAIL_BACKEND_WRITE:
            return optimistic  # 200 OK, but nothing persisted

        if scenario is Scenario.TRANSIENT_BACKEND_WRITE and app.state.attempts[key] == 1:
            return optimistic  # first attempt drops the write; a retry will persist

        if scenario is Scenario.WRONG_VALUE:
            mangled = {k: _mangle(v) for k, v in fields.items()}
            store.upsert_fields(collection, record_id, mangled)
            return optimistic  # response shows the requested value

        if scenario is Scenario.WRONG_TARGET:
            store.upsert_fields(collection, f"{record_id}__wrong", fields)
            return optimistic  # target record untouched

        if scenario is Scenario.STALE_READ:
            before = dict(store.get(collection, record_id) or {})
            persisted = store.upsert_fields(collection, record_id, fields)
            app.state.stale_cache[key] = before or persisted  # /api serves old
            return persisted

        # NONE: honest success.
        persisted = store.upsert_fields(collection, record_id, fields)
        app.state.stale_cache.pop(key, None)
        return persisted

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        return {"status": "ok", "db": app.state.db_path}

    return app


def _mangle(value: Any) -> Any:
    if isinstance(value, str) and value:
        return value[:-1] or "?"  # drop last char -> a wrong, non-empty value
    if isinstance(value, (int, float)):
        return value + 1
    return value
