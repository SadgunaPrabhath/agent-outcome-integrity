import { statusTone, verdictTone, outcomeTone, type Tone } from "@/lib/format";

type Kind = "status" | "verdict" | "outcome";

const toneFns: Record<Kind, (v: string) => Tone> = {
  status: statusTone,
  verdict: verdictTone,
  outcome: outcomeTone,
};

export function StatusPill({ value, kind }: { value: string; kind: Kind }) {
  const t = toneFns[kind](value);
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${t.text} ${t.bg} ${t.border} border`}
    >
      {value}
    </span>
  );
}
