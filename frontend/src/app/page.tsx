"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Item } from "@/lib/api";
import { AddItemForm } from "@/components/AddItemForm";
import { ItemDetail } from "@/components/ItemDetail";

export default function HomePage() {
  const [items, setItems] = useState<Item[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshingAll, setRefreshingAll] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api.listItems();
      setItems(list);
      if (list.length > 0 && (selectedId === null || !list.find((i) => i.id === selectedId))) {
        setSelectedId(list[0].id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [selectedId]);

  useEffect(() => {
    load();
  }, [load]);

  const refreshAll = async () => {
    setRefreshingAll(true);
    setError(null);
    try {
      await api.refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingAll(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Remove this tracked item?")) return;
    try {
      await api.deleteItem(id);
      if (selectedId === id) setSelectedId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const selected = items.find((i) => i.id === selectedId) ?? null;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div>
            <h1 className="text-base font-semibold">Headlight Pricer</h1>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Price your eBay headlight from real comparable sold data.
            </p>
          </div>
          <button
            onClick={refreshAll}
            disabled={refreshingAll || items.length === 0}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
          >
            {refreshingAll ? "Queuing…" : "Refresh all"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <AddItemForm onCreated={load} />

        {error && (
          <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900/40 dark:bg-rose-900/10 dark:text-rose-200">
            {error}
          </p>
        )}

        <div className="mt-6 grid gap-6 md:grid-cols-[260px_1fr]">
          <aside>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
              Tracked items
            </h2>
            <ul className="space-y-1">
              {items.length === 0 && (
                <li className="rounded-md border border-dashed border-zinc-300 px-3 py-4 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                  No items yet. Add one above.
                </li>
              )}
              {items.map((it) => (
                <li
                  key={it.id}
                  className={`group flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${
                    selectedId === it.id
                      ? "border-zinc-900 bg-zinc-100 dark:border-white dark:bg-zinc-900"
                      : "border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900"
                  }`}
                >
                  <button
                    onClick={() => setSelectedId(it.id)}
                    className="flex-1 text-left"
                  >
                    <div className="font-medium text-zinc-900 dark:text-zinc-100">
                      {it.label || it.query}
                    </div>
                    {it.label && (
                      <div className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-1">
                        {it.query}
                      </div>
                    )}
                    <div className="text-[10px] text-zinc-500 dark:text-zinc-400">
                      {it.listing_count} listings · {it.sold_count} sold
                    </div>
                  </button>
                  <button
                    onClick={() => remove(it.id)}
                    className="text-xs text-zinc-400 opacity-0 transition group-hover:opacity-100 hover:text-rose-600"
                    title="Delete"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <section>
            {selected ? (
              <ItemDetail item={selected} onChanged={load} />
            ) : (
              <div className="rounded-md border border-dashed border-zinc-300 px-4 py-12 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                Select or add a tracked item to see pricing.
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
