"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { FlagDict } from "@/lib/flags";
import { FlagChecklist } from "./FlagChecklist";

export function AddItemForm({ onCreated }: { onCreated: () => void }) {
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState("");
  const [flags, setFlags] = useState<FlagDict>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createItem({
        query: query.trim(),
        label: label.trim() || null,
        user_flags: flags,
      });
      setQuery("");
      setLabel("");
      setFlags({});
      setOpen(false);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search query, e.g. 2018 Honda Civic LED headlight driver side"
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          required
          minLength={2}
        />
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Label (optional)"
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 sm:w-48"
        />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          {open ? "Hide condition" : "Set condition"}
        </button>
        <button
          type="submit"
          disabled={submitting || query.trim().length < 2}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {submitting ? "Adding…" : "Track"}
        </button>
      </div>
      {open && (
        <div className="mt-4">
          <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
            Set the condition of <em>your</em> headlight. Comparables that
            don&apos;t match your hard filters or fall below the soft-similarity
            threshold are dropped before pricing.
          </p>
          <FlagChecklist value={flags} onChange={setFlags} />
        </div>
      )}
      {error && (
        <p className="mt-2 text-sm text-rose-600">{error}</p>
      )}
    </form>
  );
}
