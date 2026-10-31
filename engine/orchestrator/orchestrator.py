"""Orchestrator — the finite-state control loop at the center of AOIE.

State flow (with the recovery loop):

    PENDING -> RUNNING -> VERIFYING -> CLASSIFIED
                                          |
                        verified? --------+--------> FINAL
                                          |
                              not verified & recoverable
                                          |
                                     RECOVERING --> VERIFYING (re-verify)
                                          |
                            exhausted / NoRecovery --> FINAL

The loop is bounded by ``task.recovery_policy.max_retries``. Every transition is
recorded (for the dashboard timeline) and emitted to the trace.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from adapters.base import AdapterResult, AgentAdapter
from engine.classification.classifier import OutcomeClassifier
from engine.execution.context import RunContext
from engine.models import (
    AgentClaim,
    NoRecovery,
    Outcome,
    RecoveryAttempt,
    RecoveryHistory,
    RecoveryStrategy,
    RunState,
)
from engine.orchestrator.result import RunResult, StateTransition, VerificationRound
from engine.recovery.executor import RecoveryExecutor
from engine.recovery.policy import RecoveryPolicy, SafeRecoveryPolicy
from engine.verification.engine import VerificationEngine

_TERMINAL_STRATEGIES = {
    RecoveryStrategy.ESCALATE_HUMAN,
    RecoveryStrategy.MARK_UNRESOLVED,
}


class Orchestrator:
    def __init__(
        self,
        adapter: AgentAdapter,
        verification_engine: VerificationEngine | None = None,
        classifier: OutcomeClassifier | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        recovery_executor: RecoveryExecutor | None = None,
    ) -> None:
        self.adapter = adapter
        self.verifier = verification_engine or VerificationEngine()
        self.classifier = classifier or OutcomeClassifier()
        self.policy = recovery_policy or SafeRecoveryPolicy()
        self.executor = recovery_executor or RecoveryExecutor()

    async def run(self, ctx: RunContext) -> RunResult:
        task = ctx.task
        assert ctx.trace is not None
        transitions: list[StateTransition] = []
        state = RunState.PENDING

        def go(to: RunState, note: str = "") -> None:
            nonlocal state
            transitions.append(StateTransition(from_state=state, to_state=to, note=note))
            ctx.trace.add("fsm.transition", f"{state.value}->{to.value}", note=note)
            state = to

        history = RecoveryHistory()
        all_evidence = []
        rounds: list[VerificationRound] = []
        error: str | None = None

        # --- execute -----------------------------------------------------------
        go(RunState.RUNNING, "agent executing task")
        await self.adapter.initialize(ctx)
        result = await self._execute(task)
        claim, exec_error = result.claim, result.error
        ctx.trace.events.extend(result.events)  # agent actions into the run trace
        if exec_error:
            error = exec_error

        # --- initial verification ---------------------------------------------
        go(RunState.VERIFYING, "independent verification")
        report = await self.verifier.verify(ctx)
        all_evidence.extend(report.evidence)
        go(RunState.CLASSIFIED)
        http_status, err = self._signals(ctx, exec_error)
        outcome = self.classifier.classify(
            report.verdicts, task, claim, http_status=http_status, exec_error=err
        )
        rounds.append(VerificationRound(round_no=0, report=report, outcome=outcome))
        initial_outcome = outcome

        # --- recovery loop -----------------------------------------------------
        while outcome.outcome is not Outcome.VERIFIED:
            plan = self.policy.plan(outcome, task, history)
            if isinstance(plan, NoRecovery):
                ctx.trace.add(
                    "recover.declined", "no_recovery",
                    reason=plan.reason, escalate=plan.escalate,
                )
                go(RunState.FINAL, plan.reason)
                break

            go(RunState.RECOVERING, plan.strategy.value)
            execution = await self.executor.execute(plan, task, self.adapter, ctx)
            if execution.adapter_result is not None:
                claim = execution.adapter_result.claim
                ctx.trace.events.extend(execution.adapter_result.events)

            # Escalation/mark-unresolved are terminal recovery actions: record the
            # attempt and stop rather than re-verifying in a loop.
            if plan.strategy in _TERMINAL_STRATEGIES:
                history.attempts.append(
                    RecoveryAttempt(
                        attempt_no=history.count + 1,
                        strategy=plan.strategy,
                        reason=plan.reason,
                        idempotency_safe=plan.idempotency_safe,
                        executed=execution.executed,
                        outcome_after=outcome.outcome.value,
                    )
                )
                go(RunState.FINAL, plan.strategy.value)
                break

            go(RunState.VERIFYING, "re-verification after recovery")
            report = await self.verifier.verify(ctx)
            all_evidence.extend(report.evidence)
            go(RunState.CLASSIFIED)
            http_status, err = self._signals(ctx, None)
            outcome = self.classifier.classify(
                report.verdicts, task, claim, http_status=http_status, exec_error=err
            )
            rounds.append(
                VerificationRound(round_no=history.count + 1, report=report, outcome=outcome)
            )
            history.attempts.append(
                RecoveryAttempt(
                    attempt_no=history.count + 1,
                    strategy=plan.strategy,
                    reason=plan.reason,
                    idempotency_safe=plan.idempotency_safe,
                    executed=execution.executed,
                    outcome_after=outcome.outcome.value,
                )
            )

        if state is not RunState.FINAL:
            go(RunState.FINAL, "verified" if outcome.outcome is Outcome.VERIFIED else "terminal")

        await self.adapter.cleanup()

        return RunResult(
            run_id=ctx.run_id,
            task_id=task.task_id,
            adapter_name=self.adapter.name,
            agent_claim=claim,
            initial_outcome=initial_outcome,
            final_outcome=outcome,
            rounds=rounds,
            recovery_history=history,
            evidence=all_evidence,
            transitions=transitions,
            trace=ctx.trace,
            error=error,
            ended_at=datetime.now(UTC),
        )

    async def _execute(self, task) -> AdapterResult:
        """Run the adapter with the task-level timeout applied."""
        try:
            return await asyncio.wait_for(
                self.adapter.execute(task), timeout=task.timeout_s
            )
        except TimeoutError:
            return AdapterResult(
                claim=AgentClaim(claimed_success=False, message="agent timed out"),
                error="timeout",
            )
        except Exception as exc:  # noqa: BLE001 - adapter may raise anything; degrade to non-claim
            return AdapterResult(
                claim=AgentClaim(claimed_success=False, message=str(exc)), error=str(exc)
            )

    @staticmethod
    def _signals(ctx: RunContext, exec_error: str | None) -> tuple[int | None, str | None]:
        """Extract the latest mutation's HTTP status / error from the trace.

        These execution-level signals let the classifier distinguish transport
        failures (auth/timeout/5xx) that a state read alone cannot.
        """
        status: int | None = None
        err = exec_error
        assert ctx.trace is not None
        for event in reversed(ctx.trace.events):
            if event.kind == "network":
                if "status" in event.attributes:
                    status = event.attributes["status"]
                elif "error" in event.attributes:
                    err = err or event.attributes["error"]
                break
        return status, err
