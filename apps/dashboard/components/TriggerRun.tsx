"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import type { Catalog } from "@/lib/types";

export function TriggerRun({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const { data: catalog, loading, error } = useFetch<Catalog>(() => api.catalog(), []);

  const [taskId, setTaskId] = useState("");
  const [scenario, setScenario] = useState("");
  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState<string | null>(null);

  const selectedTask = useMemo(
    () => catalog?.tasks.find((t) => t.task_id === taskId),
    [catalog, taskId],
  );

  // Scenarios available for the chosen task (falls back to the global list).
  const scenarioOptions = selectedTask?.scenarios?.length
    ? selectedTask.scenarios
    : (catalog?.scenarios ?? []);

  const effectiveTask = taskId || catalog?.tasks[0]?.task_id || "";
  const effectiveScenario = scenario || scenarioOptions[0] || "none";

  async function run() {
    if (!effectiveTask) return;
    setRunning(true);
    setRunErr(null);
    try {
      const result = await api.createRun(effectiveTask, effectiveScenario);
      onDone?.();
      router.push(`/runs/${result.run_id}`);
    } catch (err) {
      setRunErr(err instanceof Error ? err.message : String(err));
      setRunning(false);
    }
  }

  return (
    <div className="rounded-lg border border-sky-500/30 bg-sky-500/[0.03] p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-sky-200">Trigger a run</div>
          <div className="text-xs text-zinc-500">
            Execute a task against the demo environment and independently verify the outcome.
          </div>
        </div>
      </div>

      {error ? (
        <div className="mt-3 text-xs text-rose-300">Could not load catalog: {error}</div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-zinc-500">Task</span>
          <select
            value={effectiveTask}
            disabled={loading || running}
            onChange={(e) => {
              setTaskId(e.target.value);
              setScenario("");
            }}
            className="min-w-56 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-100 focus:border-sky-500 focus:outline-none"
          >
            {(catalog?.tasks ?? []).map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.task_id} — {t.description}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-zinc-500">Scenario</span>
          <select
            value={effectiveScenario}
            disabled={loading || running}
            onChange={(e) => setScenario(e.target.value)}
            className="min-w-48 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-100 focus:border-sky-500 focus:outline-none"
          >
            {scenarioOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <button
          onClick={run}
          disabled={loading || running || !effectiveTask}
          className="rounded bg-sky-500 px-4 py-1.5 text-sm font-semibold text-zinc-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Running…" : "Run"}
        </button>
      </div>

      {runErr ? <div className="mt-3 text-xs text-rose-300">{runErr}</div> : null}
    </div>
  );
}
