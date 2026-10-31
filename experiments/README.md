# Experiments

Reproducible experiments built on the benchmark harness.

## Current

- **Baseline gap experiment** — the default benchmark itself: it measures the gap
  between agent-reported success and independently verified success across the
  full `task × scenario` matrix. Run:

  ```bash
  python -m scripts.run_benchmark
  ```

  Outputs `benchmark/reports/latest.{md,json}` and timestamped copies. See the
  headline numbers in the top-level README and the framing in
  [`docs/research/questions.md`](../docs/research/questions.md).

## Planned (Not yet measured)

- Multi-agent comparison once LLM/Playwright adapters land (agent-reported vs
  AOIE-verified per agent).
- Verifier ablations (reliability/cost with/without each source).
- Recovery value (verified success with vs without the recovery loop).

Experiments must only report measured numbers. Label anything unmeasured
"Not yet measured".
