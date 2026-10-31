import type { Evidence } from "@/lib/types";
import { pct, shortHash, stringify } from "@/lib/format";
import { Badge } from "@/components/Badge";

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) {
    return <div className="text-sm text-zinc-500">No evidence captured.</div>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {evidence.map((e, index) => (
        <div key={`${e.id}-${index}`} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Badge tone="blue">{e.verifier_type}</Badge>
              <span className="font-mono text-xs text-zinc-400">{e.source}</span>
            </div>
            <span className="text-[11px] text-zinc-500">conf {pct(e.confidence, 0)}</span>
          </div>

          <div className="mt-2 grid gap-2 text-xs">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-600">Expected</div>
              <div className="mt-0.5 break-words rounded bg-zinc-950/60 px-2 py-1 font-mono text-emerald-300/90">
                {stringify(e.expected_state)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-600">Observed</div>
              <div className="mt-0.5 break-words rounded bg-zinc-950/60 px-2 py-1 font-mono text-rose-300/90">
                {stringify(e.observed_state)}
              </div>
            </div>
          </div>

          <div
            className="mt-2 truncate font-mono text-[10px] text-zinc-600"
            title={e.content_hash}
          >
            {shortHash(e.content_hash, 18)}
          </div>
        </div>
      ))}
    </div>
  );
}
