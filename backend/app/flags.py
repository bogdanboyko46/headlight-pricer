"""Condition flag definitions for headlights.

Each listing and each tracked item has the same flag set. A flag is
Optional[bool]: None means unknown, True/False are explicit assertions.
"""
from __future__ import annotations

from typing import Optional

# Order matters for stable display — keep in sync with the frontend checklist.
FLAG_NAMES: list[str] = [
    "lens_clear",
    "lens_cracked",
    "housing_cracked",
    "tabs_intact",
    "moisture_inside",
    "all_bulbs_working",
    "tested",
    "oem",
    "complete_assembly",
]

# Hard filters: a comparable listing's flag must equal the user's flag exactly.
# (If user is unsure — flag is None — we don't apply that hard filter.)
HARD_FILTER_FLAGS: set[str] = {"lens_cracked", "housing_cracked", "complete_assembly"}

SOFT_FLAGS: list[str] = [f for f in FLAG_NAMES if f not in HARD_FILTER_FLAGS]

# Per-flag soft-similarity weight. Sums need not equal 1; we normalize at score time.
SOFT_WEIGHTS: dict[str, float] = {
    "lens_clear": 2.0,
    "tabs_intact": 1.5,
    "moisture_inside": 1.5,
    "all_bulbs_working": 1.0,
    "tested": 0.5,
    "oem": 1.0,
}


FlagDict = dict[str, Optional[bool]]


def empty_flags() -> FlagDict:
    return {name: None for name in FLAG_NAMES}


def coerce_flags(d: dict | None) -> FlagDict:
    out = empty_flags()
    if not d:
        return out
    for k in FLAG_NAMES:
        v = d.get(k)
        if v is None:
            out[k] = None
        elif isinstance(v, bool):
            out[k] = v
        elif isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "yes", "y", "1"}:
                out[k] = True
            elif s in {"false", "no", "n", "0"}:
                out[k] = False
            else:
                out[k] = None
        else:
            out[k] = bool(v) if v in (0, 1) else None
    return out


def hard_filter_matches(user: FlagDict, listing: FlagDict) -> bool:
    """All known hard-filter flags must match. Unknown on either side = pass."""
    for f in HARD_FILTER_FLAGS:
        u, l = user.get(f), listing.get(f)
        if u is None or l is None:
            continue
        if u != l:
            return False
    return True


def soft_similarity(user: FlagDict, listing: FlagDict) -> float:
    """Weighted match ratio over soft flags both sides have set. 0..1."""
    total = 0.0
    matched = 0.0
    for f in SOFT_FLAGS:
        u, l = user.get(f), listing.get(f)
        if u is None or l is None:
            continue
        w = SOFT_WEIGHTS.get(f, 1.0)
        total += w
        if u == l:
            matched += w
    if total == 0:
        # Nothing comparable — neutral pass (lets through listings missing soft flags
        # rather than excluding them when user hasn't picked any either).
        return 1.0
    return matched / total


def most_restrictive_flags(
    user: FlagDict, candidates: list[FlagDict]
) -> list[str]:
    """Which of the user's set flags eliminate the most candidates? Returned ordered
    most-restrictive first. Used when sample size is too small to recommend."""
    if not candidates:
        return []
    eliminations: list[tuple[str, int]] = []
    for f in FLAG_NAMES:
        u = user.get(f)
        if u is None:
            continue
        elim = sum(
            1
            for c in candidates
            if c.get(f) is not None and c.get(f) != u
        )
        if elim > 0:
            eliminations.append((f, elim))
    eliminations.sort(key=lambda x: x[1], reverse=True)
    return [f for f, _ in eliminations]
