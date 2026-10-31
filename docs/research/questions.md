# Research Framing

AOIE is built so its experiments can become a paper. Results are only reported
when measured; unmeasured quantities are labelled **Not yet measured**.

## Primary question

**How large is the gap between agent-reported task completion and independently
verified persistent task completion in tool-using workflows?**

Operationalized as the **False Completion Rate** = false success claims / all
agent success claims, and **Outcome Integrity** = verified successes / total tasks.

## Secondary questions

1. Which failure types produce the largest false-completion rates?
2. Which verification methods give the best reliability/cost tradeoff?
3. How much does automated, idempotency-safe recovery improve verified success?
4. What verification overhead (latency) does independent verification add?
5. Can independent postcondition verification improve agent reliability *without
   modifying the underlying agent*?

## Current status (measured on the included demo benchmark)

Using the scripted HTTP adapter over the controlled demo app (41 task×scenario
combinations, deterministic failure injection):

- Apparent success (agent-claimed): **70.7%**
- Verified success (AOIE): **24.4%**
- False completion rate: **65.5%**
- False-completion detection rate: **100%**
- AOIE accuracy vs ground truth: **90.2%** (the remainder is conservative
  `UNKNOWN` on stale reads — safe, not incorrect)

These characterize the *benchmark*, not real-world agents. External validity
requires the Playwright/LLM adapters on the roadmap.

## Threats to validity

- The scripted agent is not an LLM; it models a response-trusting agent.
- Failure injection is synthetic (though it mirrors real failure modes).
- Database verification assumes DB access (controlled environments only).

Reproduce all numbers with `python -m scripts.run_benchmark`.
