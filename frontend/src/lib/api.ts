import type { FlagDict, FlagName } from "./flags";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export type Item = {
  id: number;
  query: string;
  label: string | null;
  user_flags: FlagDict;
  created_at: string;
  last_refreshed_at: string | null;
  listing_count: number;
  sold_count: number;
};

export type Strategy = {
  name: "sell_fast" | "best_value" | "maximize";
  recommended_price: number | null;
  sample_size: number;
  expected_days_to_sell: number | null;
  cheaper_active_comps: number;
};

export type Recommendation = {
  item_id: number;
  has_data: boolean;
  reason: string | null;
  sample_size: number;
  excluded_outliers: number;
  median_total_price: number | null;
  strategies: Strategy[];
  most_restrictive_flags: FlagName[];
};

export type Listing = {
  id: number;
  listing_url: string;
  ebay_item_id: string | null;
  title: string | null;
  image_url: string | null;
  price: number | null;
  shipping: number | null;
  total_price: number | null;
  condition_tag: string | null;
  listing_type: string | null;
  is_sold: boolean;
  sold_date: string | null;
  days_to_sell: number | null;
  flags: FlagDict;
  flags_source: string | null;
  similarity: number;
  _outlier?: boolean;
};

export type ComparablesResponse = {
  item_id: number;
  user_flags: FlagDict;
  listings: Listing[];
};

export type HistoryPoint = {
  snapshot_at: string;
  median_price: number;
  sample_size: number;
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed: ${res.status} ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listItems: () => http<Item[]>("/items"),
  getItem: (id: number) => http<Item>(`/items/${id}`),
  createItem: (body: { query: string; label?: string | null; user_flags: FlagDict }) =>
    http<Item>("/items", { method: "POST", body: JSON.stringify(body) }),
  deleteItem: (id: number) =>
    http<{ ok: true }>(`/items/${id}`, { method: "DELETE" }),
  updateFlags: (id: number, user_flags: FlagDict) =>
    http<Item>(`/items/${id}/flags`, {
      method: "PATCH",
      body: JSON.stringify({ user_flags }),
    }),
  refresh: (id: number) =>
    http<{ id: number; scraped: number }>(`/items/${id}/refresh`, { method: "POST" }),
  refreshAll: () =>
    http<{ queued: number }>("/refresh-all", { method: "POST" }),
  recommendation: (id: number) => http<Recommendation>(`/items/${id}/recommendation`),
  comparables: (id: number) => http<ComparablesResponse>(`/items/${id}/comparables`),
  history: (id: number) => http<{ item_id: number; points: HistoryPoint[] }>(
    `/items/${id}/history`
  ),
};
