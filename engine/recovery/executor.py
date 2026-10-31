"""RecoveryExecutor — carry out a RecoveryPlan.

The executor is deliberately thin: strategy *selection* (and its safety) is the
policy's job. The executor only performs the mechanical action:

  * REFRESH_STATE     -> no agent action; the orchestrator simply re-observes.
  * RECHECK_AUTH      -> ask the adapter to re-authenticate (if it can).
  * RETRY_ACTION /
    RERUN_FAILED_STEP /
    RERUN_WORKFLOW     -> re-run the task through the adapter.
  * ESCALATE_HUMAN /
    MARK_UNRESOLVED    -> terminal; nothing to execute.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.base import AdapterResult, AgentAdapter
from engine.execution.context import RunContext
from engine.models import RecoveryPlan, RecoveryStrategy, TaskSpec

_REEXECUTE = {
    RecoveryStrategy.RETRY_ACTION,
    RecoveryStrategy.RERUN_FAILED_STEP,
    RecoveryStrategy.RERUN_WORKFLOW,
}


@dataclass
class RecoveryExecution:
    executed: bool
    adapter_result: AdapterResult | None = None
    detail: str = ""


class RecoveryExecutor:
    async def execute(
        self,
        plan: RecoveryPlan,
        task: TaskSpec,
        adapter: AgentAdapter,
        ctx: RunContext,
    ) -> RecoveryExecution:
        if ctx.trace is not None:
            ctx.trace.add(
                "recover",
                plan.strategy.value,
                reason=plan.reason,
                idempotency_safe=plan.idempotency_safe,
            )

        if plan.strategy is RecoveryStrategy.REFRESH_STATE:
            # Nothing to do to the agent; re-verification re-reads all sources.
            return RecoveryExecution(executed=True, detail="state will be re-observed")

        if plan.strategy is RecoveryStrategy.RECHECK_AUTH:
            reauth = getattr(adapter, "reauthenticate", None)
            if callable(reauth):
                await reauth()
                return RecoveryExecution(executed=True, detail="re-authenticated")
            return RecoveryExecution(executed=False, detail="adapter cannot re-auth")

        if plan.strategy in _REEXECUTE:
            result = await adapter.execute(task)
            return RecoveryExecution(
                executed=True, adapter_result=result, detail="re-executed task"
            )

        # ESCALATE_HUMAN / MARK_UNRESOLVED — terminal, no mechanical action.
        return RecoveryExecution(executed=False, detail=plan.strategy.value)
