"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { API_BASE } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview", desc: "Metrics & trigger" },
  { href: "/runs", label: "Runs", desc: "All verified runs" },
  { href: "/verification", label: "Verification", desc: "Source evidence" },
  { href: "/benchmarks", label: "Benchmarks", desc: "Suite results" },
  { href: "/failures", label: "Failures", desc: "Taxonomy" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950">
      <div className="border-b border-zinc-800 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded bg-sky-500/15 font-mono text-xs font-bold text-sky-300 ring-1 ring-sky-500/30">
            AO
          </span>
          <div>
            <div className="text-sm font-semibold text-zinc-100">AOIE</div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500">
              Outcome Integrity
            </div>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-2">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group mb-0.5 block rounded-md px-3 py-2 transition-colors ${
                active
                  ? "bg-zinc-800/80 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <div className="flex items-center gap-2 text-sm font-medium">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    active ? "bg-sky-400" : "bg-zinc-700 group-hover:bg-zinc-500"
                  }`}
                />
                {item.label}
              </div>
              <div className="ml-3.5 text-[11px] text-zinc-600">{item.desc}</div>
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-zinc-800 px-4 py-3">
        <div className="text-[10px] uppercase tracking-wider text-zinc-600">API</div>
        <div className="mt-0.5 truncate font-mono text-[11px] text-zinc-500" title={API_BASE}>
          {API_BASE}
        </div>
      </div>
    </aside>
  );
}
