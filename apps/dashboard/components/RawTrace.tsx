"use client";

import { useState } from "react";
import type { TraceEvent } from "@/lib/types";
import { fmtTime, stringify } from "@/lib/format";

export function RawTrace({ events }: { events: TraceEvent[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-sm font-semibold text-zinc-200">
          Raw trace{" "}
          <span className="ml-1 font-mono text-xs text-zinc-500">({events.length} events)</span>
        </span>
        <span className="text-zinc-500">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="max-h-[28rem] overflow-auto border-t border-zinc-800">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="sticky top-0 bg-zinc-900 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                <th className="px-3 py-1.5 font-medium">Time</th>
                <th className="px-3 py-1.5 font-medium">Kind</th>
                <th className="px-3 py-1.5 font-medium">Name</th>
                <th className="px-3 py-1.5 font-medium">Attributes</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={`${e.span_id}-${i}`} className="border-t border-zinc-800/60 align-top">
                  <td className="whitespace-nowrap px-3 py-1.5 text-zinc-500">{fmtTime(e.ts)}</td>
                  <td className="px-3 py-1.5">
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                      {e.kind}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-zinc-300">{e.name}</td>
                  <td className="px-3 py-1.5 font-mono text-zinc-500">
                    {Object.keys(e.attributes ?? {}).length ? stringify(e.attributes) : "—"}
                  </td>
                </tr>
              ))}
              {events.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-3 text-zinc-600">
                    No trace events.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
