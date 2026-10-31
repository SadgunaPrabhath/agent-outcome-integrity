"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import type { RunSummary, VerifierResult } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { VerificationTable } from "@/components/VerificationTable";
import { Card, Loading, ErrorState, EmptyState } from "@/components/States";

export default function VerificationPage() {
  const { data: runs, loading, error } = useFetch<RunSummary[]>(
    () => api.listRuns(200, 0),
    [],
  );

  const [selected, setSelected] = useState<string>("");
  const [results, setResults] = useState<VerifierResult[] | null>(null);
  const [vLoading, setVLoading] = useState(false);
  const [vError, setVError] = useState<string | null>(null);

  // Default to the latest run once the list loads.
  useEffect(() => {
    if (runs && runs.length && !selected) setSelected(runs[0].run_id);
  }, [runs, selected]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setVLoading(true);
    setVError(null);
    api
      .getVerification(selected)
      .then((r) => {
        if (!cancelled) setResults(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setVError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setVLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const selectedRun = runs?.find((r) => r.run_id === selected);

  return (
    <div>
      <PageHeader
        title="Verification"
        description="Per-source expected vs. observed state for a run. Disagreement between the UI/DOM source and the authoritative API/DB source is what exposes a false completion."
      />

      {loading ? (
        <Loading label="Loading runs…" />
      ) : error ? (
        <ErrorState message={error} />
      ) : (runs?.length ?? 0) === 0 ? (
        <EmptyState title="No runs to verify" hint="Trigger a run from the Overview page." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">Run</span>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="min-w-96 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-100 focus:border-sky-500 focus:outline-none"
            >
              {(runs ?? []).map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.task_id} · {r.scenario ?? "none"} · {r.final_outcome}
                  {r.false_completion ? " · ⚠ false completion" : ""}
                </option>
              ))}
            </select>
            {selectedRun ? (
              <Link
                href={`/runs/${selectedRun.run_id}`}
                className="rounded border border-zinc-700 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-zinc-800"
              >
                Open full run →
              </Link>
            ) : null}
          </div>

          {selectedRun ? (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-zinc-500">Agent claim:</span>
              {selectedRun.agent_claimed_success ? (
                <Badge tone="blue">SUCCESS</Badge>
              ) : (
                <Badge tone="gray">fail</Badge>
              )}
              <span className="text-zinc-500">· AOIE outcome:</span>
              <Badge tone={selectedRun.final_outcome === "VERIFIED" ? "green" : "red"}>
                {selectedRun.final_outcome}
              </Badge>
              {selectedRun.failure_class ? (
                <Badge tone="red">{selectedRun.failure_class}</Badge>
              ) : null}
            </div>
          ) : null}

          <Card title="Per-source verification results">
            {vLoading ? (
              <Loading label="Loading verification…" />
            ) : vError ? (
              <ErrorState message={vError} />
            ) : results && results.length ? (
              <VerificationTable verdicts={[]} results={results} />
            ) : (
              <EmptyState title="No verification results for this run" />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
