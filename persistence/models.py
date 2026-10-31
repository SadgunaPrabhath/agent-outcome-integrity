"""SQLAlchemy ORM models for AOIE runs, verification, evidence, recovery.

Normalized child tables (verification_results, evidence, recovery_attempts) back
the relational queries the design calls for; the full RunResult is also stored as
JSON on the run row so the run-detail endpoint can return the complete, exact
object without lossy reassembly. JSON is used selectively (trace/transitions), not
as a substitute for the relational core.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from persistence.database import Base


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128), index=True)
    adapter_name: Mapped[str] = mapped_column(String(64), index=True)
    scenario: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    agent_claimed_success: Mapped[bool] = mapped_column(Boolean)
    final_outcome: Mapped[str] = mapped_column(String(16), index=True)
    failure_class: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    false_completion: Mapped[bool] = mapped_column(Boolean, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    recovered: Mapped[bool] = mapped_column(Boolean)
    recovery_attempts: Mapped[int] = mapped_column(Integer)

    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    result_json: Mapped[dict] = mapped_column(JSON)  # full RunResult

    verifications: Mapped[list[VerificationResultRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    evidences: Mapped[list[EvidenceRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    recoveries: Mapped[list[RecoveryAttemptRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class VerificationResultRow(Base):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    postcondition_ref: Mapped[str] = mapped_column(String(128))
    verifier_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)
    evidence_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    run: Mapped[RunRow] = relationship(back_populates="verifications")


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(80), index=True)
    verifier_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(255))
    expected_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    payload_json: Mapped[dict] = mapped_column(JSON)

    run: Mapped[RunRow] = relationship(back_populates="evidences")


class RecoveryAttemptRow(Base):
    __tablename__ = "recovery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    idempotency_safe: Mapped[bool] = mapped_column(Boolean)
    executed: Mapped[bool] = mapped_column(Boolean)
    outcome_after: Mapped[str | None] = mapped_column(String(16), nullable=True)

    run: Mapped[RunRow] = relationship(back_populates="recoveries")
