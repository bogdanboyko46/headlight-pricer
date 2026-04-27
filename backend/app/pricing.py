"""Pricing recommendation engine.

Inputs: a tracked item's user flags + a list of *all* its listings (active
and sold, with parsed flags).
Outputs: per-strategy recommendation (sell-fast / best-value / maximize)
with sample size, expected days-to-sell, and number of cheaper active comps.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import numpy as np

from .config import MIN_COMPARABLE_SOLD, SOLD_WINDOW_DAYS, SOFT_SIMILARITY_THRESHOLD
from .flags import (
    FLAG_NAMES,
    FlagDict,
    HARD_FILTER_FLAGS,
    hard_filter_matches,
    most_restrictive_flags,
    soft_similarity,
)


@dataclass
class StrategyResult:
    name: str
    recommended_price: Optional[float]
    sample_size: int
    expected_days_to_sell: Optional[float]
    cheaper_active_comps: int


@dataclass
class Recommendation:
    item_id: int
    has_data: bool
    reason: Optional[str]
    sample_size: int
    excluded_outliers: int
    median_total_price: Optional[float]
    strategies: list[StrategyResult]
    most_restrictive_flags: list[str]


_STRATEGIES = [
    ("sell_fast", 25.0),
    ("best_value", 50.0),
    ("maximize", 75.0),
]


def _parse_iso_date(s: str | None) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _within_window(sold_date: str | None, *, days: int) -> bool:
    d = _parse_iso_date(sold_date)
    if not d:
        return False
    cutoff = datetime.utcnow() - timedelta(days=days)
    if d.tzinfo is not None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return d >= cutoff


def tukey_fence(values: list[float]) -> tuple[float, float]:
    """Standard Tukey 1.5*IQR fence. Returns (lo, hi)."""
    arr = np.asarray(values, dtype=float)
    if arr.size < 4:
        return float("-inf"), float("inf")
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


# eBay coarse-condition tags that signal a NEW (almost always aftermarket
# replacement) headlight. We exclude these from the comparable pool entirely:
# this app prices used-OEM headlights, not new aftermarket assemblies.
_EXCLUDED_CONDITION_TAGS: set[str] = {
    "brand new", "new", "new (other)", "new with defects",
    "new without box", "new other (see details)",
}


def _is_excluded_condition(tag: str | None) -> bool:
    if not tag:
        return False
    return tag.strip().lower() in _EXCLUDED_CONDITION_TAGS


def filter_comparables(
    user: FlagDict,
    listings: Iterable[dict],
    *,
    soft_threshold: float = SOFT_SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Apply hard filters then soft-similarity threshold. Listings tagged
    NEW / Brand New are dropped before any flag matching — they're typically
    aftermarket replacements that don't price like used-OEM comps."""
    out: list[dict] = []
    for l in listings:
        if _is_excluded_condition(l.get("condition_tag")):
            continue
        flags = l.get("flags") or {}
        if not hard_filter_matches(user, flags):
            continue
        sim = soft_similarity(user, flags)
        if sim < soft_threshold:
            continue
        l = dict(l)
        l["_similarity"] = sim
        out.append(l)
    return out


def recommend(
    item_id: int,
    user_flags: FlagDict,
    listings: list[dict],
) -> Recommendation:
    comparable_all = filter_comparables(user_flags, listings)
    comparable_sold_in_window = [
        l for l in comparable_all
        if l.get("is_sold") and _within_window(l.get("sold_date"), days=SOLD_WINDOW_DAYS)
        and l.get("total_price") is not None
    ]

    candidate_flags = [l.get("flags") or {} for l in listings]

    if len(comparable_sold_in_window) < MIN_COMPARABLE_SOLD:
        return Recommendation(
            item_id=item_id,
            has_data=False,
            reason=(
                f"Only {len(comparable_sold_in_window)} comparable sold listing(s) "
                f"in the last {SOLD_WINDOW_DAYS} days "
                f"(need {MIN_COMPARABLE_SOLD})."
            ),
            sample_size=len(comparable_sold_in_window),
            excluded_outliers=0,
            median_total_price=None,
            strategies=[
                StrategyResult(name=n, recommended_price=None,
                               sample_size=0, expected_days_to_sell=None,
                               cheaper_active_comps=0)
                for n, _ in _STRATEGIES
            ],
            most_restrictive_flags=most_restrictive_flags(user_flags, candidate_flags),
        )

    prices = [float(l["total_price"]) for l in comparable_sold_in_window]
    lo, hi = tukey_fence(prices)
    inliers = [l for l in comparable_sold_in_window
               if lo <= float(l["total_price"]) <= hi]
    excluded = len(comparable_sold_in_window) - len(inliers)
    inlier_prices = np.asarray([float(l["total_price"]) for l in inliers], dtype=float)

    median_price = float(np.median(inlier_prices)) if inlier_prices.size else None

    # Active comps for "competition" count
    comparable_active = [
        l for l in comparable_all
        if not l.get("is_sold") and l.get("total_price") is not None
    ]
    active_prices = sorted(float(l["total_price"]) for l in comparable_active)

    strategies: list[StrategyResult] = []
    for name, pct in _STRATEGIES:
        if inlier_prices.size == 0:
            strategies.append(StrategyResult(name, None, 0, None, 0))
            continue
        rec = float(np.percentile(inlier_prices, pct))
        # Days-to-sell: median of inliers at-or-below this price point
        days_pool = [
            l.get("days_to_sell") for l in inliers
            if l.get("days_to_sell") is not None and float(l["total_price"]) <= rec
        ]
        days = float(np.median(days_pool)) if days_pool else None
        cheaper = sum(1 for p in active_prices if p < rec)
        strategies.append(StrategyResult(
            name=name,
            recommended_price=round(rec, 2),
            sample_size=len(inliers),
            expected_days_to_sell=days,
            cheaper_active_comps=cheaper,
        ))

    return Recommendation(
        item_id=item_id,
        has_data=True,
        reason=None,
        sample_size=len(inliers),
        excluded_outliers=excluded,
        median_total_price=round(median_price, 2) if median_price is not None else None,
        strategies=strategies,
        most_restrictive_flags=[],
    )


def annotate_outliers(listings: list[dict]) -> list[dict]:
    """Mark which sold listings would be excluded by the Tukey fence — used
    only for the drill-down list. Doesn't filter by user flags; that's a
    different view."""
    sold = [l for l in listings if l.get("is_sold") and l.get("total_price") is not None]
    if len(sold) < 4:
        for l in listings:
            l["_outlier"] = False
        return listings
    prices = [float(l["total_price"]) for l in sold]
    lo, hi = tukey_fence(prices)
    for l in listings:
        p = l.get("total_price")
        if l.get("is_sold") and p is not None and (p < lo or p > hi):
            l["_outlier"] = True
        else:
            l["_outlier"] = False
    return listings


def recommendation_to_dict(rec: Recommendation) -> dict:
    return {
        "item_id": rec.item_id,
        "has_data": rec.has_data,
        "reason": rec.reason,
        "sample_size": rec.sample_size,
        "excluded_outliers": rec.excluded_outliers,
        "median_total_price": rec.median_total_price,
        "strategies": [asdict(s) for s in rec.strategies],
        "most_restrictive_flags": rec.most_restrictive_flags,
    }
