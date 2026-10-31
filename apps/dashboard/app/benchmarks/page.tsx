"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import type { BenchmarkLatest } from "@/lib/types";
import { pct, num, fmtTime } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { MetricCard } from "@/components/MetricCard";
import { StatusPill } from "@/components/StatusPill";
import { Badge } from "@/components/Badge";
import { Card, Loading, ErrorState, EmptyState } from "@/components/States";

export default function BenchmarksPage() {
  const { data, loading, error, reload } = useFetch<BenchmarkLatest>(
    () => api.latestBenchmark(),
    [],
  );

  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState<string | null>(null);

  async function runBenchmark() {
    setRunning(true);
    setRunErr(null);
    try {
      await api.runBenchmark();
      reload();
    } catch (e) {
      setRunErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const m = data?.metrics;
  const records = data?.records ?? [];

  return (
    <div>
      <PageHeader
        title="Benchmarks"
        description="Full-suite results: AOIE run against every task × failure scenario with known ground truth, measuring how many false completions it catches and classifies correctly."
        actions={
          <button
            onClick={runBenchmark}
            disabled={running}
            className="rounded bg-sky-500 px-4 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-sky-400 disabled:opacity-50"
          >
            {running ? "Running suite…" : "Run benchmark"}
          </button>
        }
      />

      {runErr ? <div className="mb-4 text-xs text-rose-300">{runErr}</div> : null}

      {loading ? (
        <Loading label="Loading latest benchmark…" />
      ) : error ? (
        error.includes("404") || error.toLowerCase().includes("no benchmark") ? (
          <EmptyState
            title="No benchmark report yet"
            hint="Click “Run benchmark” to execute the full suite and generate a report."
          />
        ) : (
          <ErrorState message={error} onRetry={reload} />
        )
      ) : data ? (
        <>
          <div className="mb-2 text-xs text-zinc-500">
            Generated {fmtTime(data.generated_at)} · {records.length} records
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            <MetricCard
              label="Tasks"
              value={num(m?.total_tasks ?? m?.total_runs)}
            />
            <MetricCard
              label="Apparent success"
              value={pct(m?.apparent_success_rate)}
              accent="blue"
            />
            <MetricCard
              label="Verified success"
              value={pct(m?.verified_success_rate)}
              accent="green"
            />
            <MetricCard label="False completion" value={pct(m?.false_completion_rate)} hero />
            <MetricCard
              label="Detection rate"
              value={pct(m?.detection_rate)}
              sub="false completions caught"
              accent="green"
            />
            <MetricCard
              label="AOIE accuracy"
              value={pct(m?.aoie_accuracy)}
              sub="correct classifications"
              accent="green"
            />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard label="Outcome integrity" value={pct(m?.outcome_integrity)} accent="green" />
            <MetricCard
              label="Recovery success"
              value={pct(m?.recovery_success_rate)}
              accent="amber"
            />
            <MetricCard
              label="Mean recovery attempts"
              value={m?.mean_recovery_attempts != null ? m.mean_recovery_attempts.toFixed(2) : "—"}
            />
            <MetricCard
              label="Mean verify latency"
              value={
                m?.mean_verification_latency_ms != null
                  ? `${m.mean_verification_latency_ms.toFixed(1)}ms`
                  : "—"
              }
            />
          </div>

          <div className="mt-4">
            <Card title="Benchmark records">
              {records.length === 0 ? (
                <EmptyState title="No records in this report" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500">
                        <th className="px-3 py-1.5 font-medium">Task</th>
                        <th className="px-3 py-1.5 font-medium">Scenario</th>
                        <th className="px-3 py-1.5 font-medium">Ground truth</th>
                        <th className="px-3 py-1.5 font-medium">Claim</th>
                        <th className="px-3 py-1.5 font-medium">AOIE</th>
                        <th className="px-3 py-1.5 font-medium">Failure class</th>
                        <th className="px-3 py-1.5 font-medium">False comp.</th>
                        <th className="px-3 py-1.5 font-medium">Recovered</th>
                        <th className="px-3 py-1.5 font-medium">Latency</th>
                        <th className="px-3 py-1.5 font-medium">Caught</th>
                        <th className="px-3 py-1.5 font-medium">Correct</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((r, i) => (
                        <tr
                          key={`${r.task_id}-${r.scenario}-${i}`}
                          className="border-t border-zinc-800/60"
                        >
                          <td className="px-3 py-1.5 font-medium text-zinc-200">{r.task_id}</td>
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{r.scenario}</td>
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{r.ground_truth}</td>
                          <td className="px-3 py-1.5">
                            {r.agent_claimed_success ? (
                              <Badge tone="blue">SUCCESS</Badge>
                            ) : (
                              <span className="text-zinc-600">fail</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5">
                            <StatusPill value={r.aoie_outcome} kind="outcome" />
                          </td>
                          <td className="px-3 py-1.5 font-mono text-zinc-300">
                            {r.failure_class ?? "—"}
                          </td>
                          <td className="px-3 py-1.5">
                            {r.false_completion ? (
                              <span className="text-rose-300">⚠</span>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5">
                            {r.recovered ? (
                              <Badge tone="amber">×{r.recovery_attempts}</Badge>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-zinc-500">
                            {r.verification_latency_ms}ms
                          </td>
                          <td className="px-3 py-1.5">
                            <Indicator ok={r.caught} />
                          </td>
                          <td className="px-3 py-1.5">
                            <Indicator ok={r.correct} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Indicator({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="font-mono text-emerald-400" title="yes">
      ✓
    </span>
  ) : (
    <span className="font-mono text-zinc-600" title="no">
      ·
    </span>
  );
}
