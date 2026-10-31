import { tone as toneOf } from "@/lib/format";

export interface BarDatum {
  label: string;
  value: number;
  tone?: string; // color name from lib/format tones
  hint?: string;
}

// Hand-rolled horizontal bar chart (no chart lib) for reliable builds.
export function BarChart({
  data,
  emptyLabel = "No data",
}: {
  data: BarDatum[];
  emptyLabel?: string;
}) {
  if (!data.length) {
    return <div className="py-6 text-sm text-zinc-500">{emptyLabel}</div>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d) => {
        const t = toneOf(d.tone ?? "blue");
        const width = `${Math.max((d.value / max) * 100, d.value > 0 ? 3 : 0)}%`;
        return (
          <div key={d.label} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3">
            <div
              className="truncate font-mono text-xs text-zinc-400"
              title={d.hint ?? d.label}
            >
              {d.label}
            </div>
            <div className="h-5 overflow-hidden rounded bg-zinc-800/60">
              <div
                className={`h-full rounded ${t.dot}`}
                style={{ width }}
                aria-hidden
              />
            </div>
            <div className="w-8 text-right font-mono text-xs font-semibold text-zinc-200">
              {d.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}
