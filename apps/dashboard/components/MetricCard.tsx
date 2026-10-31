import type { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  sub,
  hero = false,
  accent,
  children,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  hero?: boolean;
  accent?: "green" | "red" | "amber" | "blue" | "gray";
  children?: ReactNode;
}) {
  const accentText =
    accent === "green"
      ? "text-emerald-300"
      : accent === "red"
        ? "text-rose-300"
        : accent === "amber"
          ? "text-amber-300"
          : accent === "blue"
            ? "text-sky-300"
            : "text-zinc-100";

  return (
    <div
      className={`rounded-lg border bg-zinc-900/60 p-4 ${
        hero ? "border-rose-500/40 ring-1 ring-rose-500/20" : "border-zinc-800"
      }`}
    >
      <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      <div
        className={`mt-1 font-mono ${hero ? "text-4xl" : "text-2xl"} font-semibold ${
          hero ? "text-rose-300" : accentText
        }`}
      >
        {value}
      </div>
      {sub ? <div className="mt-1 text-xs text-zinc-500">{sub}</div> : null}
      {children}
    </div>
  );
}
