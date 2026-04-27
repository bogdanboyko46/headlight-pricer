"""Condition-flag extraction from a listing's title + item-specifics + description.

Two passes:
  1. Deterministic regex/keyword pass (cheap, fast).
  2. If critical flags are still unknown and there's enough free text to be worth
     the call, ask Claude via the Anthropic API to fill them in.

Each pass returns a FlagDict (Optional[bool] per flag). The caller merges
with regex-pass winning ties.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from .flags import FLAG_NAMES, FlagDict, empty_flags


# ---------------------------------------------------------------------------
# Regex pass

_PATTERNS: dict[str, list[tuple[str, bool]]] = {
    # (pattern, value-when-matched)
    "lens_clear": [
        (r"\b(yellow(ed|ing)?|haz(y|ed|e|ing)|oxidi[sz]ed|cloud(y|ed)|foggy|fogged|dim discolou?red|discolou?red lens)\b", False),
        (r"\b(crystal clear|clear lens(es)?|like new lens|no haz(e|ing)|no yellow(ing)?|no oxidation|polished lens|restored lens)\b", True),
    ],
    "lens_cracked": [
        (r"\b(crack(ed|s)? lens|lens (is )?crack(ed|ing)?|lens damage|broken lens|chipped lens|hole in lens)\b", True),
        (r"\b(no crack(s|ed)?|lens (is )?(intact|undamaged|not crack(ed|ing)?)|lens has no damage)\b", False),
    ],
    "housing_cracked": [
        (r"\b(crack(ed|s)? housing|housing (is )?crack(ed|ing)?|broken housing|cracked shell|cracked case)\b", True),
        (r"\b(housing (is )?(intact|undamaged|not crack(ed|ing)?)|no crack(s)? in housing)\b", False),
    ],
    "tabs_intact": [
        (r"\b(broken tab(s)?|tab(s)? (is|are)? broken|missing tab(s)?|repaired tab(s)?|chipped tab|tab broke|cracked tab(s)?)\b", False),
        (r"\b(tab(s)? (are )?(intact|good|undamaged|not broken)|all tabs (good|intact)|no broken tabs)\b", True),
    ],
    "moisture_inside": [
        (r"\b(moisture (inside|present)|condensation (inside)?|water (damage|inside)|fogging inside|wet inside|water spots? inside)\b", True),
        (r"\b(no moisture|dry inside|no condensation|no water damage|sealed)\b", False),
    ],
    "all_bulbs_working": [
        (r"\b(all bulbs work(ing)?|bulbs (all )?work|fully function(al|ing)|both beams work|low and high beam work|tested working|verified working)\b", True),
        (r"\b(bulb(s)? (out|burnt|not work(ing)?|dead)|low beam (out|dead|broken)|high beam (out|dead|broken)|one bulb out)\b", False),
    ],
    "tested": [
        (r"\b(tested( and)? (working|functional|verified)|bench tested|fully tested|verified working|tested by seller)\b", True),
        (r"\b(untested|not tested|as[- ]is|sold as is|condition unknown|for parts|parts only|parts or repair)\b", False),
    ],
    "oem": [
        (r"\b(oem|genuine|factory original|original equipment|honda factory|toyota factory|acura factory|ford factory|gm factory|stock factory)\b", True),
        (r"\b(aftermarket|replacement (assembly|part)|non[- ]oem|knock[- ]?off|generic|replica)\b", False),
    ],
    "complete_assembly": [
        (r"\b(complete assembly|full assembly|whole assembly|entire headlight|complete (head)?light)\b", True),
        (r"\b(lens only|housing only|inner only|bulb only|reflector only|no bulbs?|no housing|no lens|just the lens|just the housing)\b", False),
    ],
}


def regex_extract(text: str) -> FlagDict:
    """Apply the patterns. Last-write-wins per flag (so an explicit positive
    overrides an earlier negative when both phrases appear)."""
    out = empty_flags()
    if not text:
        return out
    lowered = text.lower()
    for flag, patterns in _PATTERNS.items():
        for pat, val in patterns:
            if re.search(pat, lowered, re.IGNORECASE):
                out[flag] = val
    return out


# ---------------------------------------------------------------------------
# LLM fallback

_FLAG_TOOL = {
    "name": "report_flags",
    "description": (
        "Report which condition flags are TRUE, FALSE, or UNKNOWN for an eBay "
        "headlight listing, based on its title, item-specifics, and description. "
        "Use UNKNOWN whenever the listing does not give clear evidence."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            f: {
                "type": "string",
                "enum": ["true", "false", "unknown"],
                "description": _FLAG_DESCRIPTIONS_PLACEHOLDER if False else "",
            }
            for f in FLAG_NAMES
        },
        "required": FLAG_NAMES,
    },
} if False else None  # built dynamically below


def _build_tool() -> dict[str, Any]:
    descriptions = {
        "lens_clear": "TRUE if lens is clear/polished/like-new. FALSE if yellowed, hazy, oxidized, cloudy.",
        "lens_cracked": "TRUE if there is a crack/hole in the lens. FALSE if explicitly intact.",
        "housing_cracked": "TRUE if the plastic housing is cracked/broken. FALSE if intact.",
        "tabs_intact": "TRUE if mounting tabs are good/undamaged. FALSE if any tab is broken/missing/repaired.",
        "moisture_inside": "TRUE if there's moisture/condensation/water inside. FALSE if explicitly dry/sealed.",
        "all_bulbs_working": "TRUE if all bulbs/beams confirmed working. FALSE if any bulb is out/burnt.",
        "tested": "TRUE if seller bench-tested/verified working. FALSE if sold as-is/untested/for parts.",
        "oem": "TRUE if OEM/genuine/factory original. FALSE if aftermarket/replica.",
        "complete_assembly": "TRUE if it's a complete headlight assembly. FALSE if it's lens-only, housing-only, etc.",
    }
    return {
        "name": "report_flags",
        "description": (
            "Report which headlight-condition flags are TRUE, FALSE, or UNKNOWN "
            "for an eBay listing. Use UNKNOWN whenever the listing does not give "
            "clear evidence — do not guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                f: {
                    "type": "string",
                    "enum": ["true", "false", "unknown"],
                    "description": descriptions[f],
                }
                for f in FLAG_NAMES
            },
            "required": FLAG_NAMES,
        },
    }


def _flags_need_llm(regex_flags: FlagDict, text_len: int) -> bool:
    """Worth calling the LLM only if regex left critical flags unknown
    AND there is enough free text to plausibly contain the answer."""
    if text_len < 80:
        return False
    critical = ("lens_clear", "tabs_intact", "moisture_inside", "complete_assembly")
    unknown_critical = sum(1 for f in critical if regex_flags.get(f) is None)
    return unknown_critical >= 2


def _to_flagdict(raw: dict[str, Any]) -> FlagDict:
    out = empty_flags()
    for f in FLAG_NAMES:
        v = raw.get(f)
        if isinstance(v, str):
            v = v.strip().lower()
            if v == "true":
                out[f] = True
            elif v == "false":
                out[f] = False
            else:
                out[f] = None
        elif isinstance(v, bool):
            out[f] = v
        else:
            out[f] = None
    return out


async def llm_extract(text: str) -> FlagDict | None:
    """Run the LLM pass. Returns None on any failure (caller falls back to regex)."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        tool = _build_tool()
        prompt = (
            "You are extracting condition flags from an eBay headlight listing. "
            "Read the text below carefully and call the report_flags tool with the "
            "best assessment of each flag.  Return UNKNOWN whenever the text does "
            "not give clear evidence — do not infer, do not guess.\n\n"
            f"---LISTING TEXT START---\n{text[:8000]}\n---LISTING TEXT END---"
        )
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=600,
            tools=[tool],
            tool_choice={"type": "tool", "name": "report_flags"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "report_flags":
                return _to_flagdict(block.input or {})
    except Exception:
        return None
    return None


def merge_flags(primary: FlagDict, secondary: FlagDict) -> FlagDict:
    """Primary wins where it has a value; fall back to secondary."""
    out = empty_flags()
    for f in FLAG_NAMES:
        out[f] = primary.get(f) if primary.get(f) is not None else secondary.get(f)
    return out


async def extract_flags(
    title: str,
    item_specifics: dict[str, str] | None,
    description: str,
) -> tuple[FlagDict, str]:
    """Returns (flags, source) where source is 'regex' | 'llm' | 'mixed'."""
    parts: list[str] = []
    if title:
        parts.append(title)
    if item_specifics:
        parts.append(
            "\n".join(f"{k}: {v}" for k, v in item_specifics.items() if v)
        )
    if description:
        parts.append(description)
    combined = "\n".join(parts)

    regex_flags = regex_extract(combined)
    source = "regex"

    if _flags_need_llm(regex_flags, len(combined)):
        llm_flags = await llm_extract(combined)
        if llm_flags is not None:
            merged = merge_flags(regex_flags, llm_flags)
            source = "mixed" if any(
                regex_flags[f] is not None for f in FLAG_NAMES
            ) else "llm"
            return merged, source

    return regex_flags, source
