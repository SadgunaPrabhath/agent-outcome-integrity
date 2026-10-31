"use client";

import { api } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import type { Metrics } from "@/lib/types";
import { pct, num, outcomeTone } from "@/lib/format";
import { PageHeader } from "@/components/PageHeader";
import { MetricCard } from "@/components/MetricCard";
import { BarChart, type BarDatum } from "@/components/BarChart";
import { Card, Loading, ErrorState, EmptyState } from "@/components/States";
import { TriggerRun } from "@/components/TriggerRun";

const OUTCOME_TONE: Record<string, string> = {
  VERIFIED: "green",
  FAILED: "red",
  PARTIAL: "amber",
  UNKNOWN: "gray",
};

export default function OverviewPage() {
  const { data, loading, error, reload } = useFetch<Metrics>(() => api.metrics(), []);

  const outcomeData: BarDatum[] = Object.entries(data?.outcome_counts ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, tone: OUTCOME_TONE[label] ?? "gray" }));

  const failureData: BarDatum[] = Object.entries(data?.failure_class_counts ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, tone: "red" }));

  const hasRuns = (data?.total_runs ?? 0) > 0;

  return (
    <div>
      <PageHeader
        title="Overview"
        description="AOIE independently verifies whether an agent actually achieved the persistent state it claimed. The gap between apparent and verified success is where false completions hide."
        actions={
          <button
            onClick={reload}
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
        }
      />

      <div className="mb-6">
        <TriggerRun onDone={reload} />
      </div>

      {loading ? (
        <Loading label="Loading metrics…" />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !hasRuns ? (
        <EmptyState
          title="No runs yet"
          hint="Trigger a run above to populate metrics, or run the benchmark suite from the Benchmarks page."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            <MetricCard label="Total runs" value={num(data?.total_runs)} />
            <MetricCard
              label="Apparent success"
              value={pct(data?.apparent_success_rate)}
              sub="what the agent claimed"
              accent="blue"
            />
            <MetricCard
              label="Verified success"
              value={pct(data?.verified_success_rate)}
              sub="what AOIE confirmed"
              accent="green"
            />
            <MetricCard
              label="False completion rate"
              value={pct(data?.false_completion_rate)}
              sub="claimed success, not verified"
              hero
            />
            <MetricCard
              label="Outcome integrity"
              value={pct(data?.outcome_integrity)}
              accent="green"
            />
            <MetricCard
              label="Recovered runs"
              value={num(data?.recovered_runs)}
              sub="verified after recovery"
              accent="amber"
            />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Outcome distribution">
              <BarChart data={outcomeData} emptyLabel="No outcomes recorded" />
            </Card>
            <Card title="Failure class frequency">
              <BarChart data={failureData} emptyLabel="No failures classified" />
            </Card>
          </div>

          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
              <span className="text-zinc-500">The gap:</span>
              <span className={`font-mono ${outcomeTone("UNKNOWN").text}`}>
                agents claimed success on{" "}
                <b className="text-sky-300">{pct(data?.apparent_success_rate)}</b> of runs
              </span>
              <span className="text-zinc-600">but AOIE could only verify</span>
              <span className="font-mono">
                <b className="text-emerald-300">{pct(data?.verified_success_rate)}</b>
              </span>
              <span className="text-zinc-600">— a</span>
              <span className="font-mono font-semibold text-rose-300">
                {pct(data?.false_completion_rate)} false-completion rate.
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
