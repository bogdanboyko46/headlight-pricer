"""Two-pass eBay scraper.

Pass 1 — search results page (active OR sold/completed). For each card:
    title, listed price, condition tag, image URL, listing URL,
    listing type (auction/buyitnow/mixed), end-date hint, shipping cost,
    days-to-sell.

Pass 2 — listing detail page. For each listing fetched in pass 1:
    item-specifics (dl.ux-labels-values), free-text description (loaded
    from the desc_ifr iframe URL — itm.ebaydesc.com).

Notes on selectors (verified live, 2026-04-27):
    - eBay's modern search results use `li.s-card.s-card--horizontal`,
      with .s-card__title / .s-card__price / .s-card__subtitle / .s-card__caption.
    - Listing detail pages use .x-item-title__mainTitle / .x-price-primary
      / .x-item-condition-text / dl.ux-labels-values.
    - Description iframe id is `desc_ifr` and its src points at
      itm.ebaydesc.com/itmdesc/{itemId} — fetchable directly without auth.
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import MAX_LISTINGS_PER_SCRAPE, DETAIL_FETCH_CONCURRENCY


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    listing_url: str
    ebay_item_id: Optional[str]
    title: str
    image_url: Optional[str]
    price: Optional[float]
    shipping: Optional[float]
    condition_tag: Optional[str]
    listing_type: Optional[str]
    is_sold: bool
    sold_date: Optional[str]
    days_to_sell: Optional[int]


@dataclass
class ListingDetail:
    item_specifics: dict[str, str] = field(default_factory=dict)
    description: str = ""
    condition_tag: Optional[str] = None  # from .x-item-condition-text on detail page


# ---------------------------------------------------------------------------
# URL helpers

def build_search_url(query: str, *, sold: bool) -> str:
    params = {"_nkw": query, "_sacat": "0"}
    if sold:
        params.update({"LH_Sold": "1", "LH_Complete": "1"})
    return "https://www.ebay.com/sch/i.html?" + urllib.parse.urlencode(params)


def itm_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"/itm/(\d+)", url)
    return m.group(1) if m else None


def desc_iframe_url(item_id: str) -> str:
    return f"https://itm.ebaydesc.com/itmdesc/{item_id}"


# ---------------------------------------------------------------------------
# Parsing helpers

_PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*\.?[0-9]{0,2})")


def parse_price(text: str | None) -> Optional[float]:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_shipping(caption_text: str | None) -> Optional[float]:
    if not caption_text:
        return None
    low = caption_text.lower()
    if "free delivery" in low or "free shipping" in low:
        return 0.0
    m = re.search(r"\$\s*([0-9]+\.?[0-9]{0,2})\s*(shipping|delivery)?", low)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


_SOLD_DATE_RE = re.compile(r"sold\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE)


def parse_sold_date(caption_text: str | None) -> Optional[str]:
    if not caption_text:
        return None
    m = _SOLD_DATE_RE.search(caption_text)
    if not m:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(m.group(1), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def detect_listing_type(card_text: str) -> str:
    low = card_text.lower()
    has_bin = "buy it now" in low
    has_bid = "bid" in low and "or best offer" not in low.replace("bid", "")
    if has_bin and ("auction" in low or has_bid):
        return "mixed"
    if has_bin:
        return "buyitnow"
    if has_bid:
        return "auction"
    return "buyitnow"


# ---------------------------------------------------------------------------
# Pass 1: search results

_SEARCH_PARSE_JS = r"""
() => {
  const out = [];
  const cards = document.querySelectorAll('li.s-card.s-card--horizontal, li.s-card');
  for (const card of cards) {
    const linkEl = card.querySelector('a.s-card__link, a[href*="/itm/"]');
    if (!linkEl) continue;
    const href = linkEl.href || '';
    const itmMatch = href.match(/\/itm\/(\d+)/);
    if (!itmMatch) continue;
    const itemId = itmMatch[1];
    if (itemId === '123456') continue;  // banner placeholder
    const titleEl = card.querySelector('.s-card__title');
    const priceEl = card.querySelector('.s-card__price');
    const subtitleEl = card.querySelector('.s-card__subtitle');
    const captions = [...card.querySelectorAll('.s-card__caption, .s-card__attribute-row')]
      .map(e => e.innerText).join('\n');
    const img = card.querySelector('img.s-card__image, img');
    const imgSrc = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';
    out.push({
      itemId,
      url: `https://www.ebay.com/itm/${itemId}`,
      title: titleEl ? titleEl.innerText.split('\n')[0].trim() : '',
      priceText: priceEl ? priceEl.innerText : '',
      conditionTag: subtitleEl ? subtitleEl.innerText.trim() : null,
      captions,
      imgSrc,
      fullText: card.innerText,
    });
  }
  return out;
}
"""


async def _solve_or_pass_challenge(page: Page) -> None:
    """eBay sometimes returns its 'Pardon Our Interruption' challenge page.
    The challenge usually clears on a single retry or a brief wait. If we're
    still stuck, the caller will see an empty result list and surface a
    clearer error."""
    try:
        if "splashui/challenge" in page.url:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
            await asyncio.sleep(2.0)
            await page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(1.0)
    except Exception:
        pass


async def _fetch_search_page(
    context: BrowserContext, query: str, *, sold: bool
) -> list[SearchResult]:
    page = await context.new_page()
    try:
        url = build_search_url(query, sold=sold)
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await _solve_or_pass_challenge(page)
        await page.wait_for_selector("li.s-card", timeout=15000)
        raw: list[dict[str, Any]] = await page.evaluate(_SEARCH_PARSE_JS)
    finally:
        await page.close()

    results: list[SearchResult] = []
    today = datetime.utcnow().date().isoformat()
    for r in raw[:MAX_LISTINGS_PER_SCRAPE]:
        price = parse_price(r.get("priceText", ""))
        shipping = parse_shipping(r.get("captions", ""))
        sold_date = parse_sold_date(r.get("captions", "")) if sold else None
        ltype = detect_listing_type(r.get("fullText", ""))
        results.append(
            SearchResult(
                listing_url=r["url"],
                ebay_item_id=r["itemId"],
                title=r.get("title", "")[:512],
                image_url=r.get("imgSrc") or None,
                price=price,
                shipping=shipping,
                condition_tag=_plausible_condition_tag(r.get("conditionTag")),
                listing_type=ltype,
                is_sold=sold,
                sold_date=sold_date if sold else None,
                days_to_sell=None,  # eBay no longer exposes start_date on results
            )
        )
    return results


# ---------------------------------------------------------------------------
# Pass 2: listing detail + description iframe

_DETAIL_PARSE_JS = r"""
() => {
  const specs = {};
  for (const dl of document.querySelectorAll('dl.ux-labels-values')) {
    const dt = dl.querySelector('dt, .ux-labels-values__labels');
    const dd = dl.querySelector('dd, .ux-labels-values__values');
    if (!dt || !dd) continue;
    const k = dt.innerText.trim().replace(/\s+/g, ' ');
    const v = dd.innerText.trim().replace(/\s+/g, ' ').slice(0, 400);
    if (k && v && !specs[k]) specs[k] = v;
  }
  // Authoritative condition string lives in .x-item-condition-text on the
  // detail page; the visible label is duplicated for screen-readers, so the
  // first non-empty line is the one to keep.
  let conditionTag = null;
  const condEl = document.querySelector('.x-item-condition-text, [data-testid="x-item-condition-text"]');
  if (condEl) {
    const lines = condEl.innerText.split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.length) conditionTag = lines[0];
  }
  return { specs, conditionTag };
}
"""

# A "condition tag" extracted from search-results is only trustworthy if it
# actually looks like a condition word. eBay's .s-card__subtitle slot is also
# (mis)used by sellers for promo lines — stars, checkmarks, "compatible w/...".
# We keep the search-page hint only when it matches a short, clean phrase.
_PLAUSIBLE_CONDITION_RE = re.compile(
    r"^(?:brand new|new(?:\s*\([^)]+\))?|new with(?:out)? .{0,20}|"
    r"pre-owned|used|open box|seller refurbished|certified -? refurbished|"
    r"manufacturer refurbished|for parts or not working|parts only)$",
    re.IGNORECASE,
)


def _plausible_condition_tag(s: str | None) -> Optional[str]:
    if not s:
        return None
    cleaned = " ".join(s.split())
    if not cleaned or len(cleaned) > 60:
        return None
    if _PLAUSIBLE_CONDITION_RE.match(cleaned):
        return cleaned
    return None


async def _fetch_detail(
    context: BrowserContext, listing: SearchResult
) -> ListingDetail:
    detail = ListingDetail()
    page = await context.new_page()
    try:
        await page.goto(listing.listing_url, wait_until="domcontentloaded", timeout=45000)
        await _solve_or_pass_challenge(page)
        try:
            await page.wait_for_selector("dl.ux-labels-values", timeout=8000)
        except Exception:
            pass
        try:
            data = await page.evaluate(_DETAIL_PARSE_JS)
            detail.item_specifics = data.get("specs", {}) or {}
            detail.condition_tag = data.get("conditionTag") or None
        except Exception:
            detail.item_specifics = {}
            detail.condition_tag = None
    finally:
        await page.close()

    if listing.ebay_item_id:
        desc_page = await context.new_page()
        try:
            await desc_page.goto(
                desc_iframe_url(listing.ebay_item_id),
                wait_until="domcontentloaded",
                timeout=20000,
            )
            try:
                detail.description = await desc_page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
            except Exception:
                detail.description = ""
        except Exception:
            detail.description = ""
        finally:
            await desc_page.close()

    return detail


# ---------------------------------------------------------------------------
# Public API

async def scrape_query(query: str) -> list[dict[str, Any]]:
    """Full two-pass scrape. Returns a list of merged listing dicts (active+sold,
    each enriched with description + item_specifics).  No DB, no flags here —
    those are layered on by the caller."""
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        # Don't waste bandwidth on images / fonts / media.
        async def _block(route):
            try:
                if route.request.resource_type in {"image", "font", "media"}:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                pass
        await context.route("**/*", _block)

        try:
            active = await _fetch_search_page(context, query, sold=False)
            sold = await _fetch_search_page(context, query, sold=True)

            # De-dup: a listing might appear in both (rare but possible).
            seen_urls: set[str] = set()
            combined: list[SearchResult] = []
            for lst in (sold, active):  # prefer sold metadata when both present
                for r in lst:
                    if r.listing_url in seen_urls:
                        continue
                    seen_urls.add(r.listing_url)
                    combined.append(r)

            # Pass 2 — detail fetch with bounded concurrency.
            sem = asyncio.Semaphore(DETAIL_FETCH_CONCURRENCY)

            async def _bounded(r: SearchResult) -> tuple[SearchResult, ListingDetail]:
                async with sem:
                    try:
                        d = await _fetch_detail(context, r)
                    except Exception:
                        d = ListingDetail()
                    return r, d

            tasks = [_bounded(r) for r in combined]
            pairs = await asyncio.gather(*tasks)

        finally:
            await context.close()
            await browser.close()

    out: list[dict[str, Any]] = []
    for r, d in pairs:
        total = None
        if r.price is not None:
            total = r.price + (r.shipping or 0.0)
        merged = asdict(r)
        # Detail-page condition is more authoritative than the search-page subtitle
        # when both are present; fall back to whichever we have.
        if d.condition_tag:
            merged["condition_tag"] = d.condition_tag
        merged.update({
            "total_price": total,
            "item_specifics": d.item_specifics,
            "description": d.description,
        })
        out.append(merged)
    return out
