import type { ReactNode } from "react";
import { tone as toneOf, type Tone } from "@/lib/format";

export function Badge({
  children,
  tone = "gray",
  title,
}: {
  children: ReactNode;
  tone?: string | Tone;
  title?: string;
}) {
  const t = typeof tone === "string" ? toneOf(tone) : tone;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${t.text} ${t.bg} ${t.border}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />
      {children}
    </span>
  );
}
