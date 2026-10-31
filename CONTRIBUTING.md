# Contributing to AOIE

Thanks for your interest. AOIE aims to be a technically credible, honest piece of
infrastructure — contributions should uphold that.

## Ground rules

- **Never fabricate results.** Benchmark numbers, accuracy, latency, and agent
  counts must come from actual runs. Label unmeasured things "Not yet measured",
  prototypes "Prototype", and incomplete work "TODO".
- **Tests are mandatory.** New behavior needs unit/integration/e2e coverage as
  appropriate. Do not weaken a test to make it pass — fix the code or explain why
  the expectation should change.
- **Keep the engine dependency-light.** `engine/` must stay importable without
  FastAPI, Playwright, or a browser.
- **Deterministic-first.** Prefer deterministic verification; add LLM/semantic
  paths only where deterministic checks genuinely cannot decide.

## Development

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev]"

pytest -q                 # full suite (unit + integration + e2e)
ruff check .              # lint
ruff check --fix .        # autofix
python -m scripts.run_benchmark   # regenerate measured metrics
```

Dashboard:

```bash
cd apps/dashboard && npm install && npm run build
```

## Pull requests

1. Branch from the default branch.
2. Ensure `pytest -q` and `ruff check` pass.
3. If you changed behavior, update the relevant `docs/` page and the README.
4. Describe *why*, not just *what*. If you changed a design decision, explain the
   reasoning.

## Project layout

See [`docs/architecture/overview.md`](docs/architecture/overview.md) for the
component map and the packages each concern lives in.
