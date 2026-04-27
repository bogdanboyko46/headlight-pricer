"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint } from "@/lib/api";

export function HistoryChart({ points }: { points: HistoryPoint[] }) {
  if (!points || points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-zinc-200 bg-white text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
        No history yet — refresh the item to record a snapshot.
      </div>
    );
  }
  const data = points.map((p) => ({
    t: new Date(p.snapshot_at).toLocaleDateString(),
    median: p.median_price,
    n: p.sample_size,
  }));
  return (
    <div className="h-64 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(120,120,120,.2)" strokeDasharray="3 3" />
          <XAxis dataKey="t" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `$${v}`}
            domain={["auto", "auto"]}
          />
          <Tooltip
            formatter={(v, name) => [
              typeof v === "number" ? `$${v.toFixed(2)}` : String(v),
              name === "median" ? "Median comparable sold" : String(name),
            ]}
            labelFormatter={(l) => `Snapshot: ${l}`}
          />
          <Line
            type="monotone"
            dataKey="median"
            stroke="#0ea5e9"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
