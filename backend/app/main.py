"""FastAPI app entry point.

Endpoints:
    POST   /items                     -> create tracked item (kicks off scrape in BG)
    GET    /items                     -> list items
    GET    /items/{id}                -> item detail
    DELETE /items/{id}                -> remove item
    PATCH  /items/{id}/flags          -> update user flags (no rescrape)
    POST   /items/{id}/refresh        -> rescrape this item
    POST   /refresh-all               -> rescrape every item (background)
    GET    /items/{id}/recommendation -> full pricing recommendation
    GET    /items/{id}/comparables    -> drill-down list w/ outlier marks
    GET    /items/{id}/history        -> median-comparable-sold over time
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

# On Windows the default asyncio loop is the Selector loop, which raises
# NotImplementedError on subprocess_exec — and Playwright needs to spawn
# Chromium via subprocess_exec. Force the Proactor loop before uvicorn boots.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import ALLOWED_ORIGINS
from .extract import extract_flags
from .flags import FLAG_NAMES, coerce_flags, soft_similarity
from .models import CreateItemRequest, UpdateFlagsRequest
from .pricing import (
    annotate_outliers,
    recommend,
    recommendation_to_dict,
)
from .scraper import scrape_query

log = logging.getLogger("headlight-pricer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="Headlight Pricer", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Internal helpers

async def _fetch_item_listings(conn, item_id: int) -> list[dict[str, Any]]:
    cur = await conn.execute(
        "SELECT * FROM listings WHERE item_id = ? ORDER BY fetched_at DESC",
        (item_id,),
    )
    rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["flags"] = db.parse_flags(d.get("flags"))
        if d.get("item_specifics"):
            try:
                d["item_specifics"] = json.loads(d["item_specifics"])
            except (json.JSONDecodeError, TypeError):
                d["item_specifics"] = {}
        else:
            d["item_specifics"] = {}
        d["is_sold"] = bool(d.get("is_sold"))
        out.append(d)
    return out


async def _scrape_and_persist(item_id: int, query: str) -> int:
    log.info("scraping item_id=%s query=%r", item_id, query)
    raw = await scrape_query(query)
    log.info("got %d listings for item_id=%s", len(raw), item_id)
    persisted = 0
    async with db.connect() as conn:
        for r in raw:
            flags, source = await extract_flags(
                r.get("title") or "",
                r.get("item_specifics") or {},
                r.get("description") or "",
            )
            await conn.execute(
                """INSERT INTO listings (
                    item_id, listing_url, ebay_item_id, title, image_url,
                    price, shipping, total_price, condition_tag, listing_type,
                    is_sold, sold_date, days_to_sell, description,
                    item_specifics, flags, flags_source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(item_id, listing_url) DO UPDATE SET
                    title=excluded.title,
                    image_url=excluded.image_url,
                    price=excluded.price,
                    shipping=excluded.shipping,
                    total_price=excluded.total_price,
                    condition_tag=excluded.condition_tag,
                    listing_type=excluded.listing_type,
                    is_sold=excluded.is_sold,
                    sold_date=excluded.sold_date,
                    days_to_sell=excluded.days_to_sell,
                    description=excluded.description,
                    item_specifics=excluded.item_specifics,
                    flags=excluded.flags,
                    flags_source=excluded.flags_source,
                    fetched_at=datetime('now')
                """,
                (
                    item_id,
                    r["listing_url"],
                    r.get("ebay_item_id"),
                    r.get("title"),
                    r.get("image_url"),
                    r.get("price"),
                    r.get("shipping"),
                    r.get("total_price"),
                    r.get("condition_tag"),
                    r.get("listing_type"),
                    1 if r.get("is_sold") else 0,
                    r.get("sold_date"),
                    r.get("days_to_sell"),
                    r.get("description"),
                    json.dumps(r.get("item_specifics") or {}),
                    json.dumps(flags),
                    source,
                ),
            )
            persisted += 1
        await conn.execute(
            "UPDATE items SET last_refreshed_at = datetime('now') WHERE id = ?",
            (item_id,),
        )

        # snapshot median comparable for history chart
        cur = await conn.execute(
            "SELECT user_flags FROM items WHERE id = ?", (item_id,)
        )
        row = await cur.fetchone()
        if row:
            user_flags = db.parse_flags(row["user_flags"])
            listings = await _fetch_item_listings(conn, item_id)
            rec = recommend(item_id, user_flags, listings)
            if rec.has_data and rec.median_total_price is not None:
                await conn.execute(
                    "INSERT INTO recommendation_history (item_id, median_price, sample_size) VALUES (?,?,?)",
                    (item_id, rec.median_total_price, rec.sample_size),
                )
        await conn.commit()
    return persisted


# ---------------------------------------------------------------------------
# Routes

@app.get("/")
async def root() -> dict[str, Any]:
    return {"ok": True, "name": "headlight-pricer", "flags": FLAG_NAMES}


@app.get("/flags")
async def list_flags() -> dict[str, Any]:
    from .flags import HARD_FILTER_FLAGS, SOFT_FLAGS, SOFT_WEIGHTS
    return {
        "all": FLAG_NAMES,
        "hard": sorted(HARD_FILTER_FLAGS),
        "soft": SOFT_FLAGS,
        "soft_weights": SOFT_WEIGHTS,
    }


@app.post("/items")
async def create_item(req: CreateItemRequest, bg: BackgroundTasks) -> dict[str, Any]:
    flags = coerce_flags(req.user_flags)
    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO items (query, label, user_flags) VALUES (?, ?, ?)",
            (req.query, req.label, json.dumps(flags)),
        )
        await conn.commit()
        item_id = cur.lastrowid
    bg.add_task(_scrape_and_persist, item_id, req.query)
    return {"id": item_id, "query": req.query, "label": req.label, "user_flags": flags}


@app.get("/items")
async def list_items() -> list[dict[str, Any]]:
    async with db.connect() as conn:
        cur = await conn.execute(
            """SELECT i.id, i.query, i.label, i.user_flags, i.created_at, i.last_refreshed_at,
                      (SELECT COUNT(*) FROM listings l WHERE l.item_id = i.id) AS listing_count,
                      (SELECT COUNT(*) FROM listings l WHERE l.item_id = i.id AND l.is_sold = 1) AS sold_count
               FROM items i ORDER BY i.created_at DESC"""
        )
        rows = await cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["user_flags"] = db.parse_flags(d.get("user_flags"))
        out.append(d)
    return out


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="item not found")
        item = dict(row)
        item["user_flags"] = db.parse_flags(item.get("user_flags"))
    return item


@app.delete("/items/{item_id}")
async def delete_item(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        await conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        await conn.commit()
    return {"ok": True}


@app.patch("/items/{item_id}/flags")
async def update_flags(item_id: int, req: UpdateFlagsRequest) -> dict[str, Any]:
    flags = coerce_flags(req.user_flags)
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id FROM items WHERE id = ?", (item_id,))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="item not found")
        await conn.execute(
            "UPDATE items SET user_flags = ? WHERE id = ?",
            (json.dumps(flags), item_id),
        )
        await conn.commit()
    return {"id": item_id, "user_flags": flags}


@app.post("/items/{item_id}/refresh")
async def refresh_item(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT query FROM items WHERE id = ?", (item_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="item not found")
        query = row["query"]
    n = await _scrape_and_persist(item_id, query)
    return {"id": item_id, "scraped": n}


@app.post("/refresh-all")
async def refresh_all(bg: BackgroundTasks) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT id, query FROM items")
        rows = await cur.fetchall()
    for r in rows:
        bg.add_task(_scrape_and_persist, r["id"], r["query"])
    return {"queued": len(rows)}


@app.get("/items/{item_id}/recommendation")
async def get_recommendation(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT user_flags FROM items WHERE id = ?", (item_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="item not found")
        user_flags = db.parse_flags(row["user_flags"])
        listings = await _fetch_item_listings(conn, item_id)
    rec = recommend(item_id, user_flags, listings)
    return recommendation_to_dict(rec)


@app.get("/items/{item_id}/comparables")
async def get_comparables(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute("SELECT user_flags FROM items WHERE id = ?", (item_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="item not found")
        user_flags = db.parse_flags(row["user_flags"])
        listings = await _fetch_item_listings(conn, item_id)
    listings = annotate_outliers(listings)
    enriched: list[dict[str, Any]] = []
    for l in listings:
        sim = soft_similarity(user_flags, l["flags"])
        d = dict(l)
        d["similarity"] = round(sim, 3)
        # Drop heavy fields the frontend doesn't need.
        d.pop("description", None)
        enriched.append(d)
    return {"item_id": item_id, "user_flags": user_flags, "listings": enriched}


@app.get("/items/{item_id}/history")
async def get_history(item_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT id FROM items WHERE id = ?", (item_id,)
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="item not found")
        cur = await conn.execute(
            "SELECT snapshot_at, median_price, sample_size FROM recommendation_history "
            "WHERE item_id = ? ORDER BY snapshot_at ASC",
            (item_id,),
        )
        rows = await cur.fetchall()
    return {
        "item_id": item_id,
        "points": [dict(r) for r in rows],
    }
