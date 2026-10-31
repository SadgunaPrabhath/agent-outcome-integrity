import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-zinc-400">
      <span className="h-3 w-3 animate-pulse rounded-full bg-sky-400" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-200">
      <div className="font-semibold text-rose-300">Something went wrong</div>
      <div className="mt-1 whitespace-pre-wrap text-rose-200/80">{message}</div>
      {onRetry ? (
        <button
          onClick={onRetry}
          className="mt-3 rounded border border-rose-500/40 px-3 py-1 text-xs font-medium text-rose-200 hover:bg-rose-500/10"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40 p-8 text-center">
      <div className="text-sm font-medium text-zinc-300">{title}</div>
      {hint ? <div className="mt-1 text-xs text-zinc-500">{hint}</div> : null}
    </div>
  );
}

export function Card({
  title,
  children,
  right,
}: {
  title?: ReactNode;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40">
      {title ? (
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
          {right}
        </div>
      ) : null}
      <div className="p-4">{children}</div>
    </div>
  );
}
