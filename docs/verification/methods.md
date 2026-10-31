# Verification Methods

AOIE verifies **typed postconditions** against ground truth using a
deterministic-first hierarchy. Confidence describes *evidence quality*, not a
probability, and is never a substitute for evidence.

## Verifier hierarchy

| Verifier | Base confidence | Authoritative | Backend (`StateSource`) |
| --- | --- | --- | --- |
| Database | 1.0 | ✅ | `SqliteStateSource` — reads the target DB file directly |
| API | 1.0 | ✅ | `HttpStateSource` — reads an authoritative read-back endpoint |
| Network | 0.9 | ❌ | mutation response (can be optimistic) |
| DOM | 0.7 | ❌ | `HttpStateSource` on the UI/optimistic view |
| Visual | 0.5 | ❌ | screenshots (roadmap) |
| Semantic | 0.4 | ❌ | LLM interpretation (roadmap) |

The engine runs **every applicable deterministic source**, not just the highest —
cross-source agreement is itself evidence, and disagreement is the signal we must
not miss.

## Postcondition types

`field_equals`, `field_matches` (regex), `exists`, `not_exists`, `count_equals`,
`state_transition`, `relation` (roadmap), `semantic` (roadmap). Matchers:
`exact`, `normalized`, `regex`, `numeric_tolerance`.

## Temporal verification

- `within_s` — poll until satisfied or the window elapses (eventual consistency).
- `must_hold_s` — the postcondition must stay satisfied across the window.

## Reconciliation

`StateReconciler` groups verifier results per postcondition:

- All conclusive results agree → `SATISFIED` / `VIOLATED` (authoritative tier decides).
- A presentational source disagreeing with an authoritative result → the
  authoritative verdict stands; the disagreement is retained for classification
  (this is how `UI_FALSE_COMPLETION` is detected).
- Two **authoritative** sources contradict → `CONFLICT` (never silently
  resolved; outcome becomes `UNKNOWN`, or `FAILED` if a violation co-occurs).
- No conclusive result → `UNKNOWN`.

## Evidence

Every result carries content-addressed (`sha256`) evidence: verifier type,
source, expected vs observed, comparison, confidence. Identical evidence
deduplicates by hash, giving a tamper-evident audit trail.
