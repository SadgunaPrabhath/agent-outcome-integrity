"""Helpers to wire AOIE's observation sources to the demo app.

Keeps the demo-specific path templates in one place so tests, the benchmark, and
the API layer all build sources identically.
"""

from __future__ import annotations

import httpx

from engine.execution.context import StateSource
from engine.models import VerifierType
from engine.observation import HttpStateSource, SqliteStateSource


def demo_sources(
    base_url: str,
    db_path: str,
    client: httpx.AsyncClient | None = None,
) -> list[StateSource]:
    """Authoritative (API read-back, DB file) + presentational (UI) sources."""
    return [
        HttpStateSource(
            VerifierType.API, base_url, "/api/{collection}/{record_id}", client=client
        ),
        HttpStateSource(
            VerifierType.DOM, base_url, "/ui/{collection}/{record_id}", client=client
        ),
        SqliteStateSource(db_path),
    ]
