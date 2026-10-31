import type { Transition } from "@/lib/types";
import { fmtTime } from "@/lib/format";

// Canonical FSM order for laying out the stepper. Recovering is optional.
const ORDER = [
  "PENDING",
  "RUNNING",
  "OBSERVING",
  "RECONCILING",
  "VERIFYING",
  "CLASSIFIED",
  "RECOVERING",
  "FINAL",
  "ERRORED",
];

function stateColor(state: string): string {
  if (state === "ERRORED") return "border-rose-500/50 bg-rose-500/10 text-rose-300";
  if (state === "FINAL") return "border-emerald-500/50 bg-emerald-500/10 text-emerald-300";
  if (state === "RECOVERING") return "border-amber-500/50 bg-amber-500/10 text-amber-300";
  return "border-sky-500/40 bg-sky-500/10 text-sky-300";
}

export function FsmTimeline({ transitions }: { transitions: Transition[] }) {
  if (!transitions.length) {
    return <div className="text-sm text-zinc-500">No state transitions recorded.</div>;
  }

  // Reconstruct the ordered chain of visited states from transitions.
  const chain: { state: string; at: string; note: string }[] = [];
  const first = transitions[0];
  chain.push({ state: first.from_state, at: first.at, note: "" });
  for (const t of transitions) {
    chain.push({ state: t.to_state, at: t.at, note: t.note });
  }

  // De-dup consecutive duplicates while preserving order & timing.
  const steps = chain.filter(
    (s, i) => i === 0 || s.state !== chain[i - 1].state || s.note,
  );

  // Sort by canonical order for a clean left-to-right stepper where possible,
  // but keep chronological fallback for unknown states.
  const sorted = [...steps].sort((a, b) => {
    const ia = ORDER.indexOf(a.state);
    const ib = ORDER.indexOf(b.state);
    if (ia === -1 || ib === -1) return 0;
    return ia - ib;
  });

  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {sorted.map((s, i) => (
        <div key={`${s.state}-${i}`} className="flex items-center gap-2">
          <div className={`rounded-md border px-3 py-1.5 ${stateColor(s.state)}`}>
            <div className="font-mono text-xs font-semibold">{s.state}</div>
            <div className="text-[10px] text-zinc-500">{fmtTime(s.at)}</div>
            {s.note ? (
              <div className="mt-0.5 max-w-40 truncate text-[10px] text-zinc-500" title={s.note}>
                {s.note}
              </div>
            ) : null}
          </div>
          {i < sorted.length - 1 ? <span className="text-zinc-600">→</span> : null}
        </div>
      ))}
    </div>
  );
}
