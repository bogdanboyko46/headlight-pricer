# Headlight Pricer

Price your eBay headlight listing from real comparable-sold data, not eBay's
coarse `Used` / `For Parts` bucket.

You give the app:

1. A search query that matches your part (e.g. `2018 Honda Civic LED headlight driver side`)
2. The actual condition of YOUR headlight — nine boolean flags (lens clear,
   tabs intact, moisture inside, OEM, complete assembly, etc.)

The backend scrapes eBay for both **active** and **sold/completed** listings
matching that query (two passes: search results + per-listing detail page +
description iframe), parses each listing's condition into the same flag
schema (regex first, optional Anthropic LLM fallback for ambiguous cases),
filters down to comparable listings (hard filters on cracks / completeness,
soft-similarity threshold on the rest), drops Tukey-fence outliers, and
returns three percentile-based price points:

- **Sell fast** — 25th percentile of comparable sold (last 60 days)
- **Best value** — median
- **Maximize** — 75th percentile

Each strategy also reports expected days-to-sell (when available) and how
many comparable active listings are currently priced *below* the
recommendation — your real competition.

If fewer than 5 comparable sold listings exist in the 60-day window the app
returns `insufficient data` rather than fabricate confidence, and tells you
which of your flags are eliminating the most candidates so you can decide
which one to relax.

## Stack

- **Frontend:** Next.js 16 (App Router) + TypeScript + Tailwind v4 + Recharts
- **Backend:** FastAPI on Python 3.11+, managed with `uv`
- **Scraper:** Playwright (Python), headless Chromium
- **Storage:** SQLite (single file, dev-only)
- **LLM:** Anthropic SDK — Claude Haiku 4.5 — *optional*; only invoked when
  the regex pass leaves critical flags ambiguous

## Layout

```
.
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app + endpoints
│   │   ├── db.py          # aiosqlite + schema
│   │   ├── models.py      # Pydantic request schemas
│   │   ├── flags.py       # Flag definitions + similarity scoring
│   │   ├── extract.py     # Regex pass + Anthropic-API fallback
│   │   ├── scraper.py     # Two-pass eBay scraper
│   │   ├── pricing.py     # Tukey IQR + percentile recommendations
│   │   └── config.py      # Env vars
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── app/page.tsx
        ├── components/
        │   ├── AddItemForm.tsx
        │   ├── FlagChecklist.tsx
        │   ├── StrategyCard.tsx
        │   ├── HistoryChart.tsx
        │   ├── ComparablesTable.tsx
        │   └── ItemDetail.tsx
        └── lib/{api.ts,flags.ts}
```

## Run locally

### Backend (FastAPI + scraper)

```bash
cd backend
uv sync
uv run playwright install chromium
# Optional: enable LLM fallback for ambiguous condition flags
cp app/.env.example app/.env
# then edit app/.env and set ANTHROPIC_API_KEY=sk-ant-...

uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API serves at <http://127.0.0.1:8000>. Hit `/` for a health check; full
endpoint list is in `app/main.py`.

If `ANTHROPIC_API_KEY` is unset the app silently falls back to regex-only
flag extraction. Recommendations still work; subtle-wording listings are
just less likely to have all their flags filled in.

### Frontend (Next.js)

```bash
cd frontend
pnpm install
# Default API URL is http://localhost:8000 — override via:
# echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
pnpm dev
```

App opens at <http://localhost:3000>. **Use `localhost`, not `127.0.0.1`** —
Next.js 16 blocks cross-origin dev resources by default and a `127.0.0.1`
host won't match the dev server's `localhost` binding.

## Workflow

1. Open the app and paste a query that matches your part.
2. Click **Set condition** and toggle each flag for *your* item.
   - Hard-filter flags (`lens_cracked`, `housing_cracked`, `complete_assembly`)
     must match exactly between you and a comparable.
   - The other flags contribute weighted soft similarity; the threshold is
     `0.5` by default (configurable via `SOFT_SIMILARITY_THRESHOLD`).
3. Click **Track** — the backend kicks off a two-pass scrape in the background.
   Wait 30–90s; refresh your browser or click **Refresh now** to see the
   recommendation populate.
4. Switch between **Sell fast / Best value / Maximize** tabs to compare
   strategies. The drill-down list at the bottom shows every comparable;
   listings excluded by the Tukey fence are visually faded.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/items` | Create tracked item, kick off scrape in background |
| GET | `/items` | List tracked items (counts + last-refresh timestamp) |
| GET | `/items/{id}` | Item detail |
| DELETE | `/items/{id}` | Remove tracked item |
| PATCH | `/items/{id}/flags` | Update user condition flags (no rescrape) |
| POST | `/items/{id}/refresh` | Rescrape this item synchronously |
| POST | `/refresh-all` | Queue a rescrape for every tracked item |
| GET | `/items/{id}/recommendation` | Strategy prices + sample size |
| GET | `/items/{id}/comparables` | Per-listing drill-down with parsed flags |
| GET | `/items/{id}/history` | Median-comparable-sold time series |
| GET | `/flags` | Flag schema + per-flag soft weight |

## Deployment

- The **frontend** is deployable to Vercel as-is. Set
  `NEXT_PUBLIC_API_URL` in the Vercel project settings to point at a
  publicly reachable backend (the local backend will not be reachable from
  the deployed frontend).
- The **backend** is intended to run locally for dev. To host it remotely
  you'll need a Playwright-friendly Linux container (the lock file already
  pins `playwright`; install Chromium with `uv run playwright install
  chromium --with-deps` in the build).

## Limitations / known caveats

- eBay's anti-bot interstitial occasionally fires on the first navigation;
  the scraper retries once after a short pause. If you hit a hard captcha
  loop, run a fresh browser session and rate-limit your queries.
- eBay no longer surfaces a listing's *start* date on the search-results
  page, so `days_to_sell` is `null` for most rows. The strategy card hides
  it when unknown.
- The seller's description iframe (`itm.ebaydesc.com`) is sometimes empty
  or login-gated. When it is, flag extraction works on title + item-specifics
  alone, which is enough for the dominant signals.
- This is a dev-grade tool — single-process SQLite, no auth, no rate
  limiting. Treat the SQLite file as throwaway.
