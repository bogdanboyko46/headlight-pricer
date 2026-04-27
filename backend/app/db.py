"""SQLite schema + connection helper. Single-process SQLite, fine for dev."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite

from .config import DB_PATH
from .flags import FLAG_NAMES, FlagDict, empty_flags

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT NOT NULL,
    label       TEXT,
    user_flags  TEXT NOT NULL,                 -- JSON FlagDict
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_refreshed_at TEXT
);

CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    listing_url     TEXT NOT NULL,
    ebay_item_id    TEXT,
    title           TEXT,
    image_url       TEXT,
    price           REAL,                       -- listed/winning price (USD)
    shipping        REAL,                       -- shipping cost (USD); 0 if free
    total_price     REAL,                       -- price + shipping
    condition_tag   TEXT,                       -- eBay's coarse tag e.g. "Used"
    listing_type    TEXT,                       -- 'auction' | 'buyitnow' | 'mixed'
    is_sold         INTEGER NOT NULL DEFAULT 0, -- 0 active, 1 sold/completed
    sold_date       TEXT,                       -- ISO date when sold
    days_to_sell    INTEGER,                    -- end - start when known
    description     TEXT,
    item_specifics  TEXT,                       -- JSON
    flags           TEXT,                       -- JSON FlagDict
    flags_source    TEXT,                       -- 'regex' | 'llm' | 'mixed'
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(item_id, listing_url)
);

CREATE INDEX IF NOT EXISTS listings_item_sold_idx
    ON listings(item_id, is_sold);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    snapshot_at TEXT NOT NULL DEFAULT (datetime('now')),
    median_price REAL,
    sample_size INTEGER
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@asynccontextmanager
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        yield db


def row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def parse_flags(s: str | None) -> FlagDict:
    if not s:
        return empty_flags()
    try:
        return {**empty_flags(), **json.loads(s)}
    except (json.JSONDecodeError, TypeError):
        return empty_flags()
