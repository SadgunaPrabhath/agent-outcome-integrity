# Agent Outcome Integrity Engine (AOIE)

**Independent outcome verification and safe recovery for tool-using agents.**

AOIE checks whether an agent's claimed action actually changed persistent state. It compares expected postconditions with independent observations, classifies the result, records supporting evidence, and retries only when failure is known and the action is safe to repeat. AOIE wraps agents; it does not replace them.

For example, an agent may click **Save** and see a success message while the server keeps the old value. AOIE checks the stored state separately, so a successful-looking interface is not treated as proof of completion.

> Status: **early-stage, working MVP.** The engine, controlled demo environment, deterministic benchmark, persistence, REST API, and dashboard are implemented and tested. A **Playwright browser adapter**, an **LLM tool-using adapter** (keyless mock for CI, real Claude backend), the **Visual/Semantic verification tiers**, and a **real LLM semantic-judge backend** are now implemented. Every number below is measured from the included benchmark — nothing is hand-authored.

---

## The central story

```
Agent:  "I changed the repository description to 'AI Research Platform'. Done."

AOIE:   NOT VERIFIED  (FAILED / UI_FALSE_COMPLETION)
        ├─ DOM (UI)        observed: "AI Research Platform"   PASS   (optimistic)
        ├─ API read-back   observed: "Old description"        FAIL   (authoritative)
        └─ Database        observed: "Old description"        FAIL   (authoritative)
        Evidence: sha256:… — the persistent state never changed.
```

The agent trusted a `200 OK`. AOIE trusted the ground truth.

---

## Why agent-reported success is insufficient

A `200 OK`, a success toast, or an agent's own "task completed" are **claims**, not proof. Persistent state can diverge from the claim because of failed network requests, backend rejection, stale/optimistic UI, race conditions, partial execution, wrong target/value, timeouts, session expiry, or external-dependency failures. AOIE never trusts the claim; it reconstructs what actually persisted and issues an **evidence-backed** verdict.

---

## Architecture

```
User Task (TaskSpec + expected postconditions)
        │
        ▼
┌─────────────────────────  Orchestrator (finite state machine)  ─────────────────────────┐
│  PENDING → RUNNING → VERIFYING → CLASSIFIED → [RECOVERING → VERIFYING]* → FINAL          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
   │            │                 │                      │
   │       AgentAdapter      Observation Layer     Verification Engine
   │       (scripted /       (API · DB · DOM ·     (per-postcondition,
   │        pluggable)        Network sources)      deterministic-first)
   │                               │                      │
   │                               ▼                      ▼
   │                        StateReconciler ──────► OutcomeClassifier
   │                        (authority tiers,       (VERIFIED / FAILED /
   │                         conflict detection)     PARTIAL / UNKNOWN + taxonomy)
   │                                                      │
   │                                                      ▼
   │                                              Recovery Engine
   │                                              (idempotency-gated policy)
   ▼
Evidence Store (content-addressed) · Execution Trace · SQLite · REST API · Dashboard
```

Full design: [`docs/architecture/overview.md`](docs/architecture/overview.md).

### Core concepts

- **TaskSpec / Postcondition** — a task carries *typed, machine-checkable* postconditions (`field_equals`, `not_exists`, `count_equals`, `state_transition`, temporal `within_s` / `must_hold_s`, …). Prose is a last resort.
- **Verification hierarchy (deterministic first)** — `Database / API (1.0) > Network (0.9) > DOM (0.7) > Visual (0.5) > Semantic (0.4)`. An LLM is used only where deterministic checks genuinely cannot decide.
- **Authority tiers** — DB and API read-back are *authoritative* (they read ground truth). DOM/UI and network responses are *presentational* (a `200` can be an optimistic lie). A presentational "success" that contradicts an authoritative "failure" is the **false-completion signal**, not a tie to break. Two authoritative sources disagreeing is a genuine **CONFLICT** and is never silently resolved into success.
- **Evidence** — every decision is backed by content-addressed (`sha256`) evidence: expected vs observed, source, confidence, comparison.
- **Idempotency-gated recovery** — a *proven* failure is safe to retry; an *unknown* outcome on a non-idempotent action (e.g. "create payment") is **never** blindly retried — it escalates.

---

## Quick start

Requires Python 3.11 or newer. Node.js 18 or newer is needed only for the dashboard. Run the API and dashboard in separate terminals.

### 1. Install the Python package

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks virtual-environment activation, use its interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Start the API

From the repository root:

```powershell
uvicorn apps.api.main:app --reload --port 8000
```

The API documentation is available at <http://localhost:8000/docs>.

### 3. Start the dashboard

In a second terminal, from the repository root:

```powershell
Set-Location apps\dashboard
npm install
npm run dev
```

Open <http://localhost:3000>. The dashboard uses `http://localhost:8000` by default. To use another API address, copy `apps/dashboard/.env.example` to `apps/dashboard/.env.local` and set `NEXT_PUBLIC_API_BASE` before starting the dashboard.

### 4. Run a benchmark

From the repository root, with the Python dependencies installed:

```powershell
python -m scripts.run_benchmark
```

The command writes measured results to `benchmark/reports/latest.md` and `latest.json`.

Trigger a false-completion run from the API:

```bash
curl -X POST http://localhost:8000/runs \
  -H 'content-type: application/json' \
  -d '{"task_id":"profile_name","scenario":"fail_backend_write"}'
# -> final_outcome.outcome = "FAILED", failure_class = "UI_FALSE_COMPLETION",
#    agent_claim.claimed_success = true   (the agent was fooled; AOIE was not)
```

---

## Demo environment & failure injection

`environments/demo_app` is a controlled FastAPI application backed by SQLite. It exposes three views that can be made to diverge on demand — an authoritative `/api` read-back, an optimistic `/ui` view, and the SQLite file itself — plus a control plane to inject deterministic failures per target:

| Scenario | What happens | Ground truth |
| --- | --- | --- |
| `none` | write persists honestly | succeeded |
| `fail_backend_write` | `200 OK` + optimistic UI, **nothing persisted** | failed |
| `wrong_value` | a wrong (non-empty) value is persisted | failed |
| `wrong_target` | the write lands on a different record | failed |
| `auth_failure` | `401`, nothing changes | failed |
| `timeout` | stalls, then `504`, nothing persisted | failed |
| `stale_read` | value persists, but authoritative read is stale | succeeded (unverifiable) |
| `transient_backend_write` | first write dropped, a retry persists | succeeded (recoverable) |

This makes every false-completion scenario reproducible and the benchmark deterministic.

---

## Verification methods

| Verifier | Source | Authoritative | Notes |
| --- | --- | --- | --- |
| Database | SQLite file read directly | ✅ | strongest evidence; controlled-env only |
| API | read-back endpoint | ✅ | independent of the mutation response |
| Network | mutation response | ❌ | a `200` can be optimistic |
| DOM | rendered/optimistic UI | ❌ | what the user/agent *sees* |
| Visual | screenshots | ❌ | roadmap |
| Semantic | LLM interpretation | ❌ | last resort, roadmap |

Details: [`docs/verification/methods.md`](docs/verification/methods.md).

---

## Recovery

After a non-verified outcome, the `SafeRecoveryPolicy` selects a strategy and enforces an **idempotency gate**:

- Proven `FAILED` → safe to retry (the action definitively did not take effect).
- `UNKNOWN` / `CONFLICT` on a non-idempotent action → **do not retry**; refresh once, else escalate.
- `AUTH_FAILURE` → re-auth; `STALE_STATE` → refresh; `PARTIAL` → re-run failed step.

Details: [`docs/recovery/policies.md`](docs/recovery/policies.md).

---

## Benchmark methodology & measured metrics

The benchmark runs a matrix of `task × scenario` combinations. For each run it records what the (scripted) agent *claims* versus what AOIE *independently determines*, and compares AOIE's verdict to the scenario's known ground truth.

**Headline metrics from the latest run** (`python -m scripts.run_benchmark`, scripted HTTP adapter, 41 task×scenario combinations):

| Metric | Value |
| --- | --- |
| Apparent success rate (agent-claimed) | **70.7%** |
| Verified success rate (AOIE) | **24.4%** |
| **False completion rate** (false claims / all success claims) | **65.5%** |
| False-completion detection rate | **100%** |
| Outcome integrity (verified / total) | **24.4%** |
| Recovery success rate | 11.4% |
| AOIE accuracy vs ground truth | **90.2%** |

Interpretation (honest): the ~10% gap in AOIE accuracy is entirely the `stale_read` scenario, where the state *was* correctly persisted but authoritative sources disagree — AOIE returns `UNKNOWN` rather than guessing, which is the safe answer, not a wrong one. The low recovery-success rate reflects that most injected faults are *persistent* (a retry hits the same fault); the one recoverable scenario (`transient_backend_write`) is recovered. These are properties of the current benchmark, not universal claims.

**Cross-agent (external validity):** the same matrix over the browser agent (`--adapter browser`, 32 form-update runs) reproduces the properties for a genuinely different agent — one that trusts an on-screen banner rather than a status code: apparent **75.0%** vs verified **25.0%**, false-completion **66.7%**, **100%** detection, accuracy **87.5%** (again pure stale-read abstention). Full analysis in [`docs/research/results.md`](docs/research/results.md).

> Reproduce: `python -m scripts.run_benchmark` (scripted) and `--adapter browser` regenerate `benchmark/reports/latest.{md,json}` and `browser_latest.{md,json}`. See [`docs/research/questions.md`](docs/research/questions.md) for the research framing.

---

## Metrics reference

Apparent success · Verified success · **False completion rate** · Partial completion · Recovery success · Mean recovery attempts · Verification latency · AOIE accuracy vs ground truth · Outcome integrity. Definitions in `benchmark/metrics/`.

---

## Dashboard

The dashboard includes Overview, Runs, Run Detail, Verification, Benchmarks, and Failure Analysis pages. Run Detail brings together the agent's claim, AOIE's verdict, execution timeline, verifier results, evidence, and any recovery attempt.

---

## Research questions

Primary: **How large is the gap between agent-reported task completion and independently verified persistent completion in tool-using workflows?** Secondary questions (failure-type distribution, verifier reliability/cost tradeoffs, recovery value, verification overhead) are in [`docs/research/questions.md`](docs/research/questions.md).

**Measured findings** — the gap, the 100% detection result, the deliberate-conservatism analysis, and how it reproduces for a browser agent — are written up in [`docs/research/results.md`](docs/research/results.md).

---

## Limitations

- **The *aggregate benchmark* uses deterministic agents, not a live LLM.** Deterministic adapters keep runs reproducible and the "claim" controllable — required to *measure* verification. Two agent classes are benchmarked (scripted HTTP, browser form), and a **third — an LLM tool-using agent** (`adapters/llm/LLMAgentAdapter`) — is implemented with a keyless mock policy for CI and a real Claude backend (`AnthropicLLMClient`, opt-in `pytest -m live`). The live LLM is not in the aggregate benchmark because a non-deterministic agent needs a different measurement design (repeated trials, distributions), which is the honest next step.
- **Database verification requires access to the target's DB** — only possible in controlled environments. For third-party targets, only API/DOM/Network apply. This is stated, not hidden.
- **Visual (0.5) and Semantic (0.4) verifiers are implemented** as last-resort tiers (`engine/verification/{visual,semantic}.py`). The Visual tier consumes real captured screenshots via a dependency-free PNG→grayscale→aHash pipeline (`engine/observation/ScreenshotStateSource`). The Semantic tier's default judge is a labelled lexical heuristic (keyless); a real LLM judge (`AnthropicSemanticJudge`) drops in via `VerificationEngine(judge=...)`, capped at the SEMANTIC tier so it can never outrank a backend read. The aggregate benchmark still exercises the deterministic tiers, where trustworthy verdicts come from.
- **Metrics are from the included demo benchmark**, not from production agents. Not yet measured against real-world agents.
- **Migrations**: the MVP uses `create_all`; Alembic migrations are a hardening follow-up.

---

## How AOIE differs from adjacent tools

- **vs browser agents** (browser-use, etc.): they *perform* tasks; AOIE *independently verifies the persistent outcome* of tasks and wraps any agent.
- **vs observability** (LangSmith, Langfuse, …): they record what the agent did and claimed; AOIE reconstructs what actually persisted and issues an independent, evidence-backed verdict. Observability trusts the trace; AOIE distrusts it by design.
- **vs replay/debugging**: replay reproduces execution; AOIE checks ground-truth state.
- **vs security monitoring**: those watch for malicious behavior; AOIE checks *correctness of outcome*.
- **vs benchmarks** (WebArena, …): those grade success once, in-house; AOIE is a reusable, agent-agnostic verification+recovery **layer**.

AOIE makes no "nobody has done this" claim; it is positioned as reusable infrastructure.

---

## Roadmap

- [x] Playwright browser adapter (drives a real HTML UI; browser-free simulator for CI + opt-in live Chromium)
- [x] Visual + Semantic verifiers (last-resort tiers; pluggable semantic judge, keyless heuristic default)
- [x] Browser agent as a first-class benchmark target (`--adapter browser`; same 100% detection)
- [x] Playwright-captured screenshots feeding the Visual verifier (dependency-free PNG→grayscale→aHash)
- [x] LLM tool-using agent adapter (`LLMAgentAdapter`; keyless mock for CI, real Claude backend, opt-in live)
- [x] Real LLM semantic-judge backend (`AnthropicSemanticJudge`; async, drops into `VerificationEngine(judge=...)`, opt-in live)
- [ ] Fold the LLM agent into the aggregate benchmark (needs a non-deterministic-agent measurement design)
- [ ] Alembic migrations; optional Postgres
- [ ] OpenTelemetry export of the execution trace
- [ ] Larger/richer task catalog and multi-step workflows
- [ ] Experiments across multiple real agents

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Tests are mandatory; run `pytest -q` and `ruff check` before opening a PR.

## License

[Apache-2.0](LICENSE).
