"""Database engine/session management for AOIE persistence (SQLite for the MVP).

SQLAlchemy 2.0 declarative. The engine URL is configurable via ``AOIE_DB_URL``
so switching to Postgres in a later phase is a config change, not a code change.
Schema is created with ``create_all`` for the MVP; Alembic migrations are a
hardening-phase follow-up (tracked in docs/architecture).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_URL = "sqlite:///aoie.db"


class Base(DeclarativeBase):
    pass


def _make_engine(url: str | None = None):
    url = url or os.environ.get("AOIE_DB_URL", DEFAULT_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


_engine = _make_engine()
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


def configure(url: str) -> None:
    """Point the module at a different database (used by tests)."""
    global _engine, SessionLocal
    _engine = _make_engine(url)
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


def init_db() -> None:
    # Import models so their tables register on Base.metadata before create_all.
    from persistence import models  # noqa: F401

    Base.metadata.create_all(_engine)


def get_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
