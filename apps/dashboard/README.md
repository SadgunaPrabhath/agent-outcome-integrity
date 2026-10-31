# AOIE Dashboard

Production dashboard for the **Agent Outcome Integrity Engine (AOIE)** — it visualizes
runs, verification evidence, and benchmark metrics from the FastAPI control-plane.

The central story it tells: an agent reports "task completed", but AOIE independently
proves the persistent backend state never changed (a **false completion**).

Built with **Next.js 15 (App Router) + TypeScript + Tailwind CSS v4**. Charts are
hand-rolled CSS/SVG (no chart library) so the build stays lightweight and reliable.

## Prerequisites

The AOIE FastAPI service must be running (defaults to `http://localhost:8000`). From the
repo root, typically:

```bash
uvicorn apps.api.main:app --reload --port 8000
```

## Getting started

```bash
cd apps/dashboard
npm install
npm run dev        # http://localhost:3000
```

Other scripts:

```bash
npm run build      # production build (used to verify the app compiles)
npm run start      # serve the production build on port 3000
```

## Configuration

The API base URL is read from `NEXT_PUBLIC_API_BASE` and defaults to
`http://localhost:8000`. To point at a different host, create `.env.local`:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

(See `.env.example`.) Because it is a `NEXT_PUBLIC_*` variable it is inlined at build
time, so re-run the build/dev server after changing it.

> Note: the API's CORS config allows `http://localhost:3000` / `http://127.0.0.1:3000`.
> Serve the dashboard from port 3000 for browser fetches to succeed.

## Pages

| Route         | Purpose                                                                        |
| ------------- | ------------------------------------------------------------------------------ |
| `/`           | Overview — metric cards (apparent vs verified success, hero false-completion rate), outcome & failure-class charts, and a **Trigger run** control. |
| `/runs`       | Runs table with client-side filters (outcome, false-completion only).          |
| `/runs/[id]`  | Run detail — agent-claim-vs-AOIE-verdict banner, FSM timeline, verification table, evidence, recovery attempts, collapsible raw trace. |
| `/verification` | Pick a run; per-source expected-vs-observed with PASS/FAIL emphasis.         |
| `/benchmarks` | Latest benchmark headline metrics, a **Run benchmark** button, and the full record table with Caught/Correct indicators. |
| `/failures`   | Ranked failure-class chart plus the full taxonomy reference.                   |

## Architecture

- `lib/api.ts` — typed API client (`api.*`) built on `fetch`, base URL from env.
- `lib/types.ts` — TypeScript mirrors of the API contract.
- `lib/format.ts` — color conventions (VERIFIED=green, FAILED=red, PARTIAL=amber, UNKNOWN=gray, CONFLICT=purple, agent SUCCESS=blue) and formatting helpers.
- `lib/useFetch.ts` — small client-side fetch hook with loading/error/reload.
- `components/` — reusable UI: `Badge`, `StatusPill`, `MetricCard`, `BarChart`, `Sidebar`, verification/evidence/timeline/trace views, plus loading/error/empty states.
