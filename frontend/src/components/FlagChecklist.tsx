"use client";

import { FLAG_LABELS, FLAG_NAMES, HARD_FILTER_FLAGS, type FlagDict, type FlagName } from "@/lib/flags";

type Tri = "true" | "false" | "unset";

function valueToTri(v: boolean | null | undefined): Tri {
  if (v === true) return "true";
  if (v === false) return "false";
  return "unset";
}

function triToValue(t: Tri): boolean | null {
  if (t === "true") return true;
  if (t === "false") return false;
  return null;
}

export function FlagChecklist({
  value,
  onChange,
  disabled = false,
}: {
  value: FlagDict;
  onChange: (next: FlagDict) => void;
  disabled?: boolean;
}) {
  const set = (name: FlagName, t: Tri) => {
    const next = { ...value };
    next[name] = triToValue(t);
    onChange(next);
  };

  return (
    <div className="space-y-2">
      {FLAG_NAMES.map((name) => {
        const isHard = HARD_FILTER_FLAGS.has(name);
        const tri: Tri = valueToTri(value[name]);
        return (
          <div
            key={name}
            className="flex items-start justify-between gap-4 rounded-md border border-zinc-200 dark:border-zinc-800 p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {FLAG_LABELS[name].label}
                </span>
                {isHard && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                    hard filter
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                {FLAG_LABELS[name].trueMeans}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1 rounded-md border border-zinc-200 dark:border-zinc-800 p-0.5 text-xs">
              {(["true", "unset", "false"] as Tri[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  disabled={disabled}
                  onClick={() => set(name, t)}
                  className={`rounded px-2.5 py-1 transition ${
                    tri === t
                      ? t === "true"
                        ? "bg-emerald-600 text-white"
                        : t === "false"
                        ? "bg-rose-600 text-white"
                        : "bg-zinc-300 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  }`}
                >
                  {t === "true" ? "yes" : t === "false" ? "no" : "—"}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
