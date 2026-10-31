# AOIE Architecture

AOIE is a **control loop**, not a linear pipeline. The canonical abstraction —

```
PRECONDITION → AGENT ACTIONS → OBSERVATIONS → STATE RECONCILIATION
→ POSTCONDITION VERIFICATION → {VERIFIED | FAILED | PARTIAL | UNKNOWN}
→ RECOVERY / RETRY / ESCALATION → RE-VERIFICATION → FINAL
```

— is realized as a finite state machine (`engine/orchestrator`) because recovery re-enters earlier states, temporal verification samples over time, and each transition must be observable.

## Components

| Component | Package | Responsibility |
| --- | --- | --- |
| Orchestrator (FSM) | `engine/orchestrator` | Drives states; bounds the recovery loop; enforces timeout; records transitions. |
| AgentAdapter | `adapters/base`, `adapters/scripted` | Runs the agent; returns a trace + the agent's own success **claim** (never trusted). |
| Observation layer | `engine/observation` | `StateSource`s that read ground truth (HTTP API/DOM, SQLite, in-memory). Observe, don't judge. |
| Verification engine | `engine/verification` | Selects verifiers per postcondition, runs them concurrently, handles temporal sampling. |
| StateReconciler | `engine/reconciliation` | Combines verifier results using authority tiers; raises CONFLICT on authoritative contradiction. |
| OutcomeClassifier | `engine/classification` | Maps verdicts (+ execution signals) to outcome + failure taxonomy. |
| Recovery | `engine/recovery`, `engine/policies` | Idempotency-gated strategy selection and execution. |
| Evidence / tracing | `engine/models`, `engine/tracing` | Content-addressed evidence; structured trace; secret redaction. |
| Persistence | `persistence` | SQLAlchemy models + repository (SQLite for MVP). |
| API | `apps/api` | FastAPI control plane consumed by the dashboard. |
| Dashboard | `apps/dashboard` | Next.js UI. |
| Benchmark | `benchmark` | Task catalog, scenario ground truth, runner, metrics, reports. |
| Demo env | `environments/demo_app` | Controlled app with deterministic failure injection. |

## Key design decisions

1. **FSM over pipeline** — makes recovery/temporal/observability tractable.
2. **Authority tiers in reconciliation** — DB/API decide; DOM/Network corroborate. A presentational "success" over an authoritative "failure" is the false-completion signal; two authoritative sources disagreeing is a genuine, never-auto-resolved CONFLICT.
3. **Deterministic-first verification** — LLMs only when deterministic checks cannot decide.
4. **Idempotency gate on recovery** — proven-failed is retryable; unknown+non-idempotent escalates.
5. **Scripted adapter first** — reproducible measurement requires a controllable "claim". LLM/browser adapters are additive.
6. **SQLite + modular monolith for the MVP** — Postgres/Redis/Celery deferred until the verification core is proven.

## Data model

Relational core (`persistence/models.py`): `runs`, `verification_results`, `evidence`, `recovery_attempts`. The full `RunResult` is also stored as JSON on the run row for lossless detail; JSON is used selectively (trace, transitions), not as a substitute for the relational core. Migrations (Alembic) are a hardening follow-up; the MVP uses `create_all`.
