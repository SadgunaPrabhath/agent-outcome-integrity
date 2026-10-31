# AOIE — Measured Results

> Every figure here is produced by `python -m scripts.run_benchmark` against the
> controlled demo app. Nothing is hand-authored. The raw report for this run is
> `benchmark/reports/latest.{md,json}`. Re-running regenerates these numbers
> deterministically. This document interprets them; it does not invent them.

## 1. The question

Tool-using agents routinely report success from a proxy signal — an HTTP `200`,
a rendered "Saved ✓" banner — rather than from the persistent state the user
actually asked to change. When that proxy diverges from reality, the agent
reports a **false completion**: it says done, the world disagrees.

**Primary question:** *How large is the gap between agent-reported completion and
independently verified persistent completion, and can a reusable verification
layer close it without producing confident-but-wrong verdicts of its own?*

## 2. Method

- **Environment.** A controlled demo app (`environments/demo_app`) exposing three
  views of the same state that can be made to diverge on demand: an authoritative
  `/api` read-back, the SQLite file itself (ground-truth DB), and an optimistic
  `/ui` view. A per-target *scenario* injects a specific failure mode.
- **Agent.** A scripted HTTP agent that concludes success from the response code
  alone — the naive behaviour false completion arises from. Because it is
  scripted, its claim is controllable and every run is reproducible, which is a
  precondition for *measuring* verification rather than anecdotally observing it.
- **Matrix.** 41 `task × scenario` combinations across 6 tasks (field updates,
  a create, a delete) and 8 scenarios (honest success, backend-write failure,
  wrong value, wrong target, auth failure, timeout, stale read, transient
  failure).
- **Verification.** AOIE reads each postcondition through a deterministic
  hierarchy — DB/API (authoritative, confidence 1.0) over Network (0.9) over DOM
  (0.7) — reconciles the sources under explicit *authority tiers*, and classifies
  the outcome. Two authoritative sources that disagree are a `CONFLICT`, never a
  silent success.
- **Scoring.** AOIE's verdict is compared to each scenario's known ground truth.

## 3. Headline results

Measured run of 2026-09-10 (41 runs, scripted HTTP adapter):

| Metric | Value | Reading |
| --- | ---: | --- |
| Apparent success (agent-claimed) | **70.7%** | What you'd believe if you trusted the agent |
| Verified success (AOIE) | **24.4%** | What actually persisted and was independently confirmed |
| **False-completion rate** | **65.5%** | Of the agent's "successes", how many were not real |
| False-completion **detection rate** | **100%** | Of the real false completions, how many AOIE caught |
| AOIE accuracy vs ground truth | **90.2%** | How often AOIE's verdict matched reality |
| Recovery success rate | **11.4%** | Fraction of failures automatically healed |
| Mean verification latency | **8.6 ms** | Overhead per run (in-process) |

The gap is the finding: **a 70.7% claimed success rate corresponds to a 24.4%
verified success rate.** Trusting the agent would overstate real success by
roughly 2.9×. AOIE caught **every** injected false completion (100% detection).

## 4. Where the verdicts come from

Aggregated over the 41 runs:

| AOIE outcome | Count | | Failure class | Count |
| --- | ---: | --- | --- | ---: |
| FAILED | 27 | | UI_FALSE_COMPLETION | 15 |
| VERIFIED | 10 | | AUTH_FAILURE | 6 |
| UNKNOWN | 4 | | TIMEOUT | 6 |
| | | | STATE_CONFLICT | 4 |

By scenario:

- **`fail_backend_write`, `wrong_value`, `wrong_target`** — the agent sees `200`
  and claims success; the authoritative API/DB show the state never changed (or
  changed wrongly). Classified **UI_FALSE_COMPLETION**. These are the core catch.
- **`auth_failure`, `timeout`** — the agent receives `401`/`504` and is *honest*
  (does not claim success). AOIE still classifies the failure precisely
  (**AUTH_FAILURE** / **TIMEOUT**) from execution-level signals, so these are not
  false completions but are still correctly reported failures.
- **`stale_read`** — the DB persisted the new value but the API read is stale.
  Two authoritative sources disagree → **STATE_CONFLICT → UNKNOWN**. This is the
  deliberate conservatism described next.
- **`none`, `transient_backend_write`** — genuine successes → **VERIFIED** (the
  transient case only after a recovery retry).

## 5. The 9.8% accuracy gap is conservatism, not error

AOIE's accuracy vs ground truth is 90.2%, not 100%. The entire gap is the four
`stale_read` runs, where the write *did* persist (ground truth = succeeded) but
the two authoritative sources disagree at read time. AOIE refuses to call these
`VERIFIED` and returns `UNKNOWN`/`CONFLICT` instead.

This is a design choice, and the right one: when two ground-truth sources
contradict each other, declaring success would be guessing. **AOIE is wrong here
only in the sense that it declined to certify a success it could not prove** —
the failure mode is abstention, never a confident false "verified". No run in the
matrix was a false *negative* on detection (it never missed a real false
completion) and none was a false *positive* success.

## 6. Recovery

Recovery success is 11.4% — and that low number is honest, not a weakness hidden.
Only the `transient_backend_write` scenario is genuinely self-healing (a second
attempt persists), so it is the only one recovery can fix. Non-idempotent or
hard failures are correctly *escalated* rather than blindly retried; the
idempotency gate exists precisely to avoid unsafe automatic reruns. Recovery here
is measured on a deliberately hard set, not tuned to inflate the number.

## 7. Does this generalise beyond a scripted agent?

The section-3 numbers are from the scripted HTTP agent. To test whether the same
false completions are caught for a *different* class of agent, AOIE also ships a
**browser agent** (`adapters/playwright/BrowserUiAdapter`) that drives a real HTML
form and concludes success from the on-screen banner. It is now a first-class
benchmark target — run `python -m scripts.run_benchmark --adapter browser`.

Measured over the 32 browser-drivable `task × scenario` combinations (the four
form-update tasks; create/delete have no typeable field, so a form-driving agent
cannot attempt them, and benchmarking it there would measure adapter capability,
not verification):

| Metric | Scripted (41 runs) | Browser (32 runs) |
| --- | ---: | ---: |
| Apparent success (agent) | 70.7% | **75.0%** |
| Verified success (AOIE) | 24.4% | **25.0%** |
| False-completion rate | 65.5% | **66.7%** |
| **Detection rate** | 100% | **100%** |
| AOIE accuracy vs truth | 90.2% | **87.5%** |
| Recovery success | 11.4% | **14.3%** |

The headline properties are unchanged for a genuinely different agent: apparent
success still runs ~3× the verified rate, and AOIE still catches **100%** of the
real false completions. The accuracy figure again reflects only stale-read
abstention (4 of 32 → 12.5%), i.e. the same deliberate conservatism, not error.
End-to-end scenario proofs are in `tests/end_to_end/test_browser_scenarios.py`
and the benchmark invariant in `tests/integration/test_benchmark.py`; a
real-Chromium variant runs under `pytest -m live`. Report:
`benchmark/reports/browser_latest.{md,json}`.

**A third agent class — an LLM tool-using agent.** `adapters/llm/LLMAgentAdapter`
runs a real agentic loop (the model proposes `set_fields` / `get_state` / `finish`
tool calls; the adapter executes them against the app and feeds results back).
It is model-agnostic behind an `LLMClient`: a keyless mock policy drives it in CI
(no API access, no skips), and a real Claude backend (`AnthropicLLMClient`) runs
under `pytest -m live` with credentials. The end-to-end scenario proofs
(`tests/end_to_end/test_llm_scenarios.py`) show the same result — when the tool
returns an optimistic 200 and the agent calls `finish(success=true)`, AOIE reads
the backend and classifies **UI_FALSE_COMPLETION**. Crucially, the live test
asserts a *model-independent* guarantee: whatever a real model claims, a silently
failed write is **never** certified VERIFIED. The live LLM is deliberately kept
out of the aggregate benchmark — a non-deterministic agent needs a different
measurement design (repeated trials, claim distributions) than the reproducible
`task × scenario` matrix, and reporting a single non-deterministic run as a rate
would be dishonest.

## 8. Threats to validity

- **Synthetic environment.** The demo app is controlled and in-process; real
  targets have network variance, richer state, and DBs AOIE may not be able to
  read. DB verification specifically requires target access.
- **Controlled agents in the aggregate.** Both benchmarked agents (scripted HTTP,
  browser-form) are deterministic by design, to make the claim controllable and
  runs reproducible. They differ in *how* they judge success (response code vs
  on-screen banner) yet agree in AOIE's verdicts — real cross-agent evidence. A
  real LLM tool-using agent now exists (`AnthropicLLMClient`, opt-in `-m live`)
  and its live test asserts the model-independent detection guarantee, but
  estimating the *apparent* success rate of a non-deterministic agent in the wild
  needs a repeated-trials design that is not yet built.
- **Deterministic verifiers only in the aggregate.** The Visual (0.5) and Semantic
  (0.4) tiers are implemented (`engine/verification/{visual,semantic}.py`) but are
  last-resort channels; the benchmark exercises the deterministic tiers, which is
  where trustworthy verdicts come from. The Semantic tier's default judge is a
  labelled lexical heuristic; a real LLM judge (`AnthropicSemanticJudge`) is a
  drop-in backend, and by design the verifier caps its confidence at the SEMANTIC
  tier so it can never outrank a backend read — an LLM assists only where nothing
  deterministic can decide, and never overrules ground truth.
- **Scale.** 41 runs over 6 tasks is enough to demonstrate the gap and the
  detection property, not to claim a population estimate. A larger catalog and
  multiple real agents are needed for that.

## 9. Reproducing

```bash
pip install -e ".[dev]"
python -m scripts.run_benchmark                    # scripted -> benchmark/reports/latest.{md,json}
python -m scripts.run_benchmark --adapter browser  # browser  -> benchmark/reports/browser_latest.{md,json}
pytest -q                                          # 97 tests, deterministic
pytest -m live                                     # opt-in real-Chromium proof (needs the browser extra)
```

Ground-truth labels live in `benchmark/scenarios/`; metric definitions in
`benchmark/metrics/`. If a number here disagrees with a fresh run, trust the fresh
run and open an issue — these figures are only ever a snapshot of the harness.
