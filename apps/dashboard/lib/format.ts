// Presentation helpers: color conventions, formatting.

// Tailwind class tuples: [text, bg, border] used by badges/pills.
export type Tone = {
  text: string;
  bg: string;
  border: string;
  dot: string;
};

const TONES: Record<string, Tone> = {
  green: { text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30", dot: "bg-emerald-400" },
  red: { text: "text-rose-300", bg: "bg-rose-500/10", border: "border-rose-500/30", dot: "bg-rose-400" },
  amber: { text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30", dot: "bg-amber-400" },
  gray: { text: "text-zinc-300", bg: "bg-zinc-500/10", border: "border-zinc-500/30", dot: "bg-zinc-400" },
  purple: { text: "text-violet-300", bg: "bg-violet-500/10", border: "border-violet-500/30", dot: "bg-violet-400" },
  blue: { text: "text-sky-300", bg: "bg-sky-500/10", border: "border-sky-500/30", dot: "bg-sky-400" },
};

export function tone(name: keyof typeof TONES | string): Tone {
  return TONES[name] ?? TONES.gray;
}

export function outcomeTone(outcome: string | null | undefined): Tone {
  switch (outcome) {
    case "VERIFIED":
      return TONES.green;
    case "FAILED":
      return TONES.red;
    case "PARTIAL":
      return TONES.amber;
    case "UNKNOWN":
      return TONES.gray;
    default:
      return TONES.gray;
  }
}

export function verdictTone(verdict: string | null | undefined): Tone {
  switch (verdict) {
    case "SATISFIED":
      return TONES.green;
    case "VIOLATED":
      return TONES.red;
    case "CONFLICT":
      return TONES.purple;
    case "UNKNOWN":
      return TONES.gray;
    default:
      return TONES.gray;
  }
}

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "PASS":
      return TONES.green;
    case "FAIL":
      return TONES.red;
    case "INCONCLUSIVE":
      return TONES.amber;
    default:
      return TONES.gray;
  }
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return String(value);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortHash(hash: string | null | undefined, head = 10): string {
  if (!hash) return "—";
  const body = hash.startsWith("sha256:") ? hash.slice(7) : hash;
  return `${hash.startsWith("sha256:") ? "sha256:" : ""}${body.slice(0, head)}…`;
}

export function stringify(value: unknown): string {
  if (value === null || value === undefined) return "∅ (none)";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 0);
  } catch {
    return String(value);
  }
}
