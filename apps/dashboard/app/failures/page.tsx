"use client";

import { api } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import type { Metrics } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { BarChart, type BarDatum } from "@/components/BarChart";
import { Card, Loading, ErrorState } from "@/components/States";
import { FAILURE_CLASSES, failureInfo } from "@/lib/failureClasses";

export default function FailuresPage() {
  const { data, loading, error, reload } = useFetch<Metrics>(() => api.metrics(), []);

  const counts = data?.failure_class_counts ?? {};
  const ranked = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = ranked.reduce((acc, [, v]) => acc + v, 0);

  const chartData: BarDatum[] = ranked.map(([label, value]) => ({
    label,
    value,
    tone: "red",
    hint: failureInfo(label).description,
  }));

  return (
    <div>
      <PageHeader
        title="Failure analysis"
        description="The AOIE failure taxonomy, ranked by how often each class has been observed. Every classification is derived from independent evidence, not the agent's self-report."
        actions={
          <button
            onClick={reload}
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
        }
      />

      {loading ? (
        <Loading label="Loading failure metrics…" />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={`Observed failure classes${total ? ` (${total})` : ""}`}>
            {ranked.length === 0 ? (
              <div className="py-6 text-sm text-zinc-500">
                No failures classified yet. Trigger failing scenarios from the Overview page or
                run the benchmark suite.
              </div>
            ) : (
              <BarChart data={chartData} />
            )}
          </Card>

          <Card title="Taxonomy reference">
            <div className="flex flex-col divide-y divide-zinc-800/70">
              {FAILURE_CLASSES.map((f) => {
                const n = counts[f.id] ?? 0;
                return (
                  <div key={f.id} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="mt-0.5 w-8 shrink-0 text-right font-mono text-sm font-semibold text-zinc-300">
                      {n}
                    </div>
                    <div>
                      <div className="font-mono text-xs font-semibold text-zinc-200">
                        {f.id}
                      </div>
                      <div className="mt-0.5 text-xs text-zinc-500">{f.description}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
