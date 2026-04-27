"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ComparablesResponse,
  type HistoryPoint,
  type Item,
  type Recommendation,
} from "@/lib/api";
import type { FlagDict } from "@/lib/flags";
import { ComparablesTable } from "./ComparablesTable";
import { FlagChecklist } from "./FlagChecklist";
import { HistoryChart } from "./HistoryChart";
import { StrategyCard } from "./StrategyCard";

export function ItemDetail({
  item,
  onChanged,
}: {
  item: Item;
  onChanged: () => void;
}) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [comp, setComp] = useState<ComparablesResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [flags, setFlags] = useState<FlagDict>(item.user_flags);
  const [savingFlags, setSavingFlags] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [r, c, h] = await Promise.all([
        api.recommendation(item.id),
        api.comparables(item.id),
        api.history(item.id),
      ]);
      setRec(r);
      setComp(c);
      setHistory(h.points);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [item.id]);

  useEffect(() => {
    setFlags(item.user_flags);
    reload();
  }, [item.id, item.user_flags, reload]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refresh(item.id);
      await reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  const saveFlags = async () => {
    setSavingFlags(true);
    setError(null);
    try {
      await api.updateFlags(item.id, flags);
      await reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingFlags(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            {item.label || item.query}
          </h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {item.listing_count} listings · {item.sold_count} sold ·
            last refresh {item.last_refreshed_at ?? "never"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
          >
            {refreshing ? "Refreshing…" : "Refresh now"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900/40 dark:bg-rose-900/10 dark:text-rose-200">
          {error}
        </div>
      )}

      <StrategyCard rec={rec} />

      <details className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Adjust your item&apos;s condition flags
        </summary>
        <div className="space-y-3 px-4 pb-4">
          <FlagChecklist value={flags} onChange={setFlags} disabled={savingFlags} />
          <button
            onClick={saveFlags}
            disabled={savingFlags}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {savingFlags ? "Saving…" : "Save flags"}
          </button>
        </div>
      </details>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Median comparable sold over time
        </h3>
        <HistoryChart points={history} />
      </div>

      <ComparablesTable listings={comp?.listings ?? []} />
    </div>
  );
}
