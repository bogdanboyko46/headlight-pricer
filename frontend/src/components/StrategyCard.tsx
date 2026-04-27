"use client";

import { useState } from "react";
import type { Recommendation, Strategy } from "@/lib/api";
import { FLAG_LABELS, type FlagName } from "@/lib/flags";

const STRATEGY_LABEL: Record<Strategy["name"], { title: string; blurb: string }> = {
  sell_fast: { title: "Sell fast",  blurb: "25th percentile of comparable sold." },
  best_value: { title: "Best value", blurb: "Median of comparable sold." },
  maximize:   { title: "Maximize",   blurb: "75th percentile of comparable sold." },
};

function fmtUSD(n: number | null): string {
  if (n === null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtDays(n: number | null): string {
  if (n === null || Number.isNaN(n)) return "—";
  if (n < 1) return "<1 day";
  if (n === 1) return "1 day";
  return `${Math.round(n)} days`;
}

export function StrategyCard({ rec }: { rec: Recommendation | null }) {
  const [active, setActive] = useState<Strategy["name"]>("best_value");

  if (!rec) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
        Loading recommendation…
      </div>
    );
  }

  if (!rec.has_data) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm dark:border-amber-900/40 dark:bg-amber-900/10">
        <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
          Insufficient data
        </h3>
        <p className="mt-1 text-sm text-amber-800 dark:text-amber-300">{rec.reason}</p>
        {rec.most_restrictive_flags.length > 0 && (
          <div className="mt-3 text-sm text-amber-900 dark:text-amber-200">
            <p className="mb-1 font-medium">Most restrictive flags (loosen one to open up comps):</p>
            <ul className="ml-4 list-disc">
              {rec.most_restrictive_flags.slice(0, 3).map((f: FlagName) => (
                <li key={f}>{FLAG_LABELS[f]?.label ?? f}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  const current = rec.strategies.find((s) => s.name === active);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex border-b border-zinc-200 dark:border-zinc-800">
        {rec.strategies.map((s) => (
          <button
            key={s.name}
            onClick={() => setActive(s.name)}
            className={`flex-1 px-3 py-2 text-sm font-medium transition ${
              active === s.name
                ? "border-b-2 border-zinc-900 text-zinc-900 dark:border-white dark:text-white"
                : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {STRATEGY_LABEL[s.name].title}
          </button>
        ))}
      </div>
      {current && (
        <div className="p-5">
          <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {STRATEGY_LABEL[current.name].blurb}
          </p>
          <p className="mt-1 text-3xl font-semibold tabular-nums text-zinc-900 dark:text-white">
            {fmtUSD(current.recommended_price)}
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
            <div>
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">Sample</dt>
              <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                {current.sample_size}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">Days to sell</dt>
              <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                {fmtDays(current.expected_days_to_sell)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">Cheaper active</dt>
              <dd className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                {current.cheaper_active_comps}
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
            {rec.excluded_outliers > 0
              ? `${rec.excluded_outliers} outlier${rec.excluded_outliers === 1 ? "" : "s"} excluded by Tukey fence.`
              : "No outliers excluded."}{" "}
            Median comparable sold: {fmtUSD(rec.median_total_price)}.
          </p>
        </div>
      )}
    </div>
  );
}
