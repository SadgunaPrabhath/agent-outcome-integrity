"""Demo-app persistence — a tiny generic record store on SQLite (stdlib only).

Kept deliberately simple and ORM-free so that:
  * AOIE's DatabaseVerifier can read the very same file independently, and
  * the whole demo has zero heavy dependencies.

A record is (collection, record_id, fields-as-JSON). This one shape covers every
benchmark task type (profile, settings, project, item, order, ...).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class RecordStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    collection TEXT NOT NULL,
                    record_id  TEXT NOT NULL,
                    fields     TEXT NOT NULL,
                    PRIMARY KEY (collection, record_id)
                )
                """
            )

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM records")

    def seed(self, collection: str, record_id: str, fields: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO records (collection, record_id, fields) "
                "VALUES (?, ?, ?)",
                (collection, record_id, json.dumps(fields)),
            )

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fields FROM records WHERE collection = ? AND record_id = ?",
                (collection, record_id),
            ).fetchone()
        return json.loads(row["fields"]) if row else None

    def upsert_fields(
        self, collection: str, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        current = self.get(collection, record_id) or {}
        current.update(fields)
        self.seed(collection, record_id, current)
        return current

    def delete(self, collection: str, record_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM records WHERE collection = ? AND record_id = ?",
                (collection, record_id),
            )
            return cur.rowcount > 0

    def count(self, collection: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM records WHERE collection = ?",
                (collection,),
            ).fetchone()
        return int(row["n"])
