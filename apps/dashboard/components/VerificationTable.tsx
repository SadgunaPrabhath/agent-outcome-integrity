import type { ReconciledVerdict, VerifierResult } from "@/lib/types";
import { StatusPill } from "@/components/StatusPill";
import { stringify, pct } from "@/lib/format";

// Detect the disagreement that reveals a false completion: a UI/DOM source
// PASSes while an authoritative source (api/database) FAILs on the same postcondition.
function isRevealingSource(vr: VerifierResult, all: VerifierResult[]): boolean {
  const authoritative = new Set(["api", "database"]);
  const uiPass = vr.verifier_type === "dom" && vr.status === "PASS";
  const authFail =
    authoritative.has(vr.verifier_type) && vr.status === "FAIL";
  if (authFail) {
    const uiSaysPass = all.some(
      (o) =>
        o.postcondition_ref === vr.postcondition_ref &&
        o.verifier_type === "dom" &&
        o.status === "PASS",
    );
    if (uiSaysPass) return true;
  }
  if (uiPass) {
    const authSaysFail = all.some(
      (o) =>
        o.postcondition_ref === vr.postcondition_ref &&
        authoritative.has(o.verifier_type) &&
        o.status === "FAIL",
    );
    if (authSaysFail) return true;
  }
  return false;
}

export function VerificationTable({
  verdicts,
  results,
}: {
  verdicts: ReconciledVerdict[];
  results: VerifierResult[];
}) {
  // Group verifier results by postcondition.
  const byRef = new Map<string, VerifierResult[]>();
  for (const r of results) {
    const list = byRef.get(r.postcondition_ref) ?? [];
    list.push(r);
    byRef.set(r.postcondition_ref, list);
  }

  // Ensure postconditions that only appear in verdicts still render.
  const refs = new Set<string>([
    ...verdicts.map((v) => v.postcondition_ref),
    ...byRef.keys(),
  ]);

  if (refs.size === 0) {
    return <div className="text-sm text-zinc-500">No verification results.</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      {[...refs].map((ref) => {
        const verdict = verdicts.find((v) => v.postcondition_ref === ref);
        const sources = byRef.get(ref) ?? verdict?.contributing ?? [];
        return (
          <div key={ref} className="rounded-lg border border-zinc-800 bg-zinc-900/40">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
              <div className="font-mono text-xs text-zinc-300">{ref}</div>
              <div className="flex items-center gap-2">
                {verdict ? (
                  <>
                    <StatusPill value={verdict.verdict} kind="verdict" />
                    <span className="text-[11px] text-zinc-500">
                      conf {pct(verdict.confidence, 0)}
                    </span>
                    {verdict.conflict ? (
                      <span className="rounded bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300 ring-1 ring-violet-500/30">
                        CONFLICT
                      </span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-[11px] text-zinc-500">no reconciled verdict</span>
                )}
              </div>
            </div>

            {verdict?.reason ? (
              <div className="border-b border-zinc-800/60 px-3 py-2 text-xs text-zinc-400">
                {verdict.reason}
              </div>
            ) : null}

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-3 py-1.5 font-medium">Source</th>
                    <th className="px-3 py-1.5 font-medium">Status</th>
                    <th className="px-3 py-1.5 font-medium">Expected</th>
                    <th className="px-3 py-1.5 font-medium">Observed</th>
                    <th className="px-3 py-1.5 font-medium">Conf</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s, i) => {
                    const revealing = isRevealingSource(s, results);
                    return (
                      <tr
                        key={`${s.verifier_type}-${i}`}
                        className={`border-t border-zinc-800/60 ${
                          revealing ? "bg-rose-500/[0.06]" : ""
                        }`}
                      >
                        <td className="px-3 py-1.5">
                          <span className="font-mono text-zinc-300">{s.verifier_type}</span>
                          {revealing ? (
                            <span
                              className="ml-2 text-[10px] font-semibold text-rose-300"
                              title="This source disagreement reveals the false completion"
                            >
                              ⚠ disagreement
                            </span>
                          ) : null}
                        </td>
                        <td className="px-3 py-1.5">
                          <StatusPill value={s.status} kind="status" />
                        </td>
                        <td className="max-w-xs truncate px-3 py-1.5 font-mono text-zinc-400" title={stringify(s.expected)}>
                          {stringify(s.expected)}
                        </td>
                        <td className="max-w-xs truncate px-3 py-1.5 font-mono text-zinc-400" title={stringify(s.observed)}>
                          {stringify(s.observed)}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-zinc-500">
                          {pct(s.confidence, 0)}
                        </td>
                      </tr>
                    );
                  })}
                  {sources.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-2 text-zinc-600">
                        No per-source results.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
