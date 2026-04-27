"use client";

import { useMemo, useState } from "react";
import type { Listing } from "@/lib/api";
import { FLAG_LABELS, FLAG_NAMES, type FlagName } from "@/lib/flags";

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function FlagPill({ flag, value }: { flag: FlagName; value: boolean | null | undefined }) {
  if (value === null || value === undefined) return null;
  const label = FLAG_LABELS[flag]?.label ?? flag;
  return (
    <span
      title={label}
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
        value
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
          : "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200"
      }`}
    >
      {value ? "✓" : "✗"} {label.length > 18 ? label.slice(0, 16) + "…" : label}
    </span>
  );
}

export function ComparablesTable({ listings }: { listings: Listing[] }) {
  const [showAll, setShowAll] = useState(false);
  const [filter, setFilter] = useState<"all" | "sold" | "active">("sold");

  const filtered = useMemo(() => {
    let out = listings;
    if (filter === "sold") out = out.filter((l) => l.is_sold);
    if (filter === "active") out = out.filter((l) => !l.is_sold);
    out = [...out].sort(
      (a, b) => (b.similarity ?? 0) - (a.similarity ?? 0)
    );
    return showAll ? out : out.slice(0, 25);
  }, [listings, showAll, filter]);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Comparable listings ({listings.length})
        </h3>
        <div className="flex gap-1 rounded-md border border-zinc-200 p-0.5 text-xs dark:border-zinc-800">
          {(["sold", "active", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded px-2 py-1 ${
                filter === f
                  ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      <div className="max-h-[480px] overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-3 py-2">Item</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Sim</th>
              <th className="px-3 py-2">Flags</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((l) => (
              <tr
                key={l.id}
                className={`border-t border-zinc-100 align-top dark:border-zinc-900 ${
                  l._outlier ? "opacity-50" : ""
                }`}
              >
                <td className="px-3 py-2">
                  <a
                    href={l.listing_url}
                    target="_blank"
                    rel="noreferrer"
                    className="line-clamp-2 max-w-[28ch] text-zinc-900 hover:underline dark:text-zinc-100"
                  >
                    {l.title ?? "(untitled)"}
                  </a>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {l.condition_tag ?? "—"}
                  </p>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  <div className="font-medium text-zinc-900 dark:text-zinc-100">
                    {fmt(l.total_price)}
                  </div>
                  {l.shipping ? (
                    <div className="text-xs text-zinc-500 dark:text-zinc-400">
                      +{fmt(l.shipping)} ship
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs">
                  <span
                    className={`inline-flex rounded px-1.5 py-0.5 ${
                      l.is_sold
                        ? "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200"
                        : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    {l.is_sold ? "sold" : "active"}
                  </span>
                  {l.is_sold && l.sold_date && (
                    <p className="mt-0.5 text-[10px] text-zinc-500">{l.sold_date}</p>
                  )}
                  {l._outlier && (
                    <p className="mt-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                      excluded (Tukey)
                    </p>
                  )}
                </td>
                <td className="px-3 py-2 tabular-nums text-zinc-600 dark:text-zinc-300">
                  {(l.similarity ?? 0).toFixed(2)}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {FLAG_NAMES.map((f) => (
                      <FlagPill key={f} flag={f} value={l.flags?.[f]} />
                    ))}
                    {l.flags_source && (
                      <span className="text-[10px] text-zinc-400">
                        ({l.flags_source})
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-zinc-500">
                  No listings yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!showAll && listings.length > 25 && (
        <div className="border-t border-zinc-200 px-4 py-2 text-center dark:border-zinc-800">
          <button
            onClick={() => setShowAll(true)}
            className="text-xs text-zinc-600 hover:underline dark:text-zinc-300"
          >
            Show all {listings.length}
          </button>
        </div>
      )}
    </div>
  );
}
