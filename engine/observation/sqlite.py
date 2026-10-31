"""SqliteStateSource — observe ground-truth state by reading a SQLite file.

This is the DatabaseVerifier's backend: it reads the demo app's persistence file
*directly*, independent of the app's read APIs and caches. That independence is
the point — it is the strongest evidence of what was actually persisted.

Only usable in controlled environments where AOIE has DB access (documented as a
stated limitation for third-party targets).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from engine.execution.context import StateSource
from engine.models import Observation, Postcondition, PostconditionType, TargetRef, VerifierType


class SqliteStateSource(StateSource):
    def __init__(
        self,
        db_path: str,
        *,
        table: str = "records",
        collection_key: str = "collection",
        id_key: str = "record_id",
    ) -> None:
        self.verifier_type = VerifierType.DATABASE
        self.db_path = db_path
        self.table = table
        self.collection_key = collection_key
        self.id_key = id_key

    async def read(self, pc: Postcondition, target: TargetRef) -> Observation:
        return await asyncio.to_thread(self._read_sync, pc, target)

    def _read_sync(self, pc: Postcondition, target: TargetRef) -> Observation:
        collection = target.locator.get("collection", target.entity)
        record_id = target.locator.get("record_id", target.entity_id or "")
        src = f"db:{self.db_path}#{collection}/{record_id}"
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                if pc.type is PostconditionType.COUNT_EQUALS:
                    row = conn.execute(
                        f"SELECT COUNT(*) AS n FROM {self.table} "
                        f"WHERE {self.collection_key} = ?",
                        (collection,),
                    ).fetchone()
                    return Observation(
                        observer_type=self.verifier_type,
                        source=src,
                        state={"count": int(row["n"])},
                    )
                row = conn.execute(
                    f"SELECT fields FROM {self.table} "
                    f"WHERE {self.collection_key} = ? AND {self.id_key} = ?",
                    (collection, record_id),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return Observation(observer_type=self.verifier_type, source=src, error=str(exc))

        if row is None:
            return Observation(
                observer_type=self.verifier_type, source=src, state={"exists": False}
            )
        fields: dict[str, Any] = json.loads(row["fields"])
        fields.setdefault("exists", True)
        return Observation(observer_type=self.verifier_type, source=src, state=fields)
