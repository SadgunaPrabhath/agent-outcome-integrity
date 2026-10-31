# Recovery Policies

After a non-verified outcome, AOIE decides **whether** and **how** to recover.
The overriding rule (Section 12 of the design): *never blindly repeat an action
that might have already taken effect.*

## The idempotency gate

Two questions (`engine/policies/idempotency.py`):

1. **Is the task inherently idempotent?** Declared per action in the TaskSpec
   (`Idempotency.IDEMPOTENT / NON_IDEMPOTENT / UNKNOWN`); inferred from
   postcondition shape when no hints are given (`field_equals`, `not_exists`,
   `state_transition` are idempotent; `exists`/`count_equals` imply creation and
   are not).
2. **Is a retry safe *now*, given the verified outcome?**
   - `FAILED` (proven the state did **not** change) → retry is safe even for a
     non-idempotent action.
   - `UNKNOWN` / `PARTIAL` (could-have-happened) → retry only if the task is
     inherently idempotent.
   - Otherwise → not safe.

The canonical case: a "create payment" whose verification is `UNKNOWN` is
**never** retried — it escalates.

## Strategy selection (`SafeRecoveryPolicy`)

| Failure class / outcome | Strategy |
| --- | --- |
| `AUTH_FAILURE` | `RECHECK_AUTH` |
| `STALE_STATE` | `REFRESH_STATE` |
| `STATE_CONFLICT` / `UNKNOWN` | `REFRESH_STATE` once, then `ESCALATE_HUMAN` |
| `WRONG_TARGET` | `RERUN_FAILED_STEP` |
| `PARTIAL` | `RERUN_FAILED_STEP` |
| persistence/backend/network/timeout/wrong-value/UI-false-completion | `RETRY_ACTION` |

Mutating strategies (`RETRY_ACTION`, `RERUN_FAILED_STEP`, `RERUN_WORKFLOW`) pass
through the idempotency gate; non-mutating strategies (refresh/auth/escalate) are
always allowed. The loop is bounded by `recovery_policy.max_retries`;
`ESCALATE_HUMAN` / `MARK_UNRESOLVED` are terminal.

Every attempt is recorded (`RecoveryAttempt`) with the strategy, reason,
`idempotency_safe` flag, whether it executed, and the re-verified outcome — so the
decision to retry or escalate is fully auditable.
