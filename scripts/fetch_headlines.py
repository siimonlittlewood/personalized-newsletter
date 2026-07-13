"""
Deterministic fetch/filter step for the morning newsletter pipeline.

Pulls candidate headlines (Currents API + niche RSS feeds) and market data
(Twelve Data), tags headlines against config/interests.yaml, and writes one
JSON blob to output/latest.json for the newsletter agent to read.

This script does no personalization/ranking/summarizing itself — that's left
to the LLM agent step, which has better judgment for nuance than keyword
matching does. This script's only job is to gather and tag candidates
reliably and cheaply.
"""
import calendar
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml
import yfinance
from dateutil import parser as dateparser
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"

load_dotenv(ROOT / ".env")
CURRENTS_API_KEY = os.environ.get("CURRENTS_API_KEY")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY")

MAX_AGE_DAYS = 7

# Obvious speculation/rumor headlines get dropped before they ever reach the
# agent step — user feedback was explicit: "I only want actual sports news,
# not rumors." This is a blunt keyword filter, not NLP, so it'll miss subtler
# cases; the agent step should still apply its own judgment on top of this.
RUMOR_PATTERN = re.compile(
    r"\b(rumors?|rumours?|reportedly|could be headed|sources say|per report|per sources|makes.{0,20}claim)\b",
    re.IGNORECASE,
)


def is_recent(published_at):
    """True if published_at (a datetime or None) is within MAX_AGE_DAYS.

    Items with no parseable date are kept rather than dropped — an unknown
    date is not evidence the story is stale, and RSS feeds don't always
    populate a date field.
    """
    if published_at is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    return published_at >= cutoff


def parse_rss_date(entry):
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)


def parse_currents_date(article):
    raw = article.get("published")
    if not raw:
        return None
    try:
        return dateparser.parse(raw)
    except (ValueError, TypeError):
        return None


def load_config():
    interests = yaml.safe_load((CONFIG_DIR / "interests.yaml").read_text())
    sources = yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text())
    tickers = json.loads((CONFIG_DIR / "tickers.json").read_text())["tickers"]
    return interests, sources, tickers


def match_interests(text, interests):
    """Return the list of interest categories whose keywords appear in text.

    Uses word-boundary matching, not plain substring — a naive `"rap" in text`
    check would false-positive on words like "Raptors" or "AI" inside "said".
    """
    matched = []
    for category, keywords in interests.items():
        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(category)
                break
    return matched


def fetch_currents(sources, interests):
    if not CURRENTS_API_KEY:
        print("  [skip] CURRENTS_API_KEY not set")
        return []

    items = []
    cfg = sources["apis"]["currents"]
    for category in cfg["categories"]:
        try:
            resp = requests.get(
                cfg["base_url"],
                params={"apiKey": CURRENTS_API_KEY, "category": category, "language": "en"},
                timeout=15,
            )
            resp.raise_for_status()
            articles = resp.json().get("news", [])
        except requests.RequestException as exc:
            print(f"  [warn] Currents API category={category} failed: {exc}")
            continue

        for a in articles:
            title = a.get("title", "")
            description = a.get("description", "")
            if RUMOR_PATTERN.search(f"{title} {description}"):
                continue
            published_at = parse_currents_date(a)
            if not is_recent(published_at):
                continue
            matched = match_interests(f"{title} {description}", interests)
            items.append(
                {
                    "title": title,
                    "description": description,
                    "url": a.get("url"),
                    "source": a.get("author") or "Currents",
                    "feed_category": category,
                    "matched_interests": matched,
                    "published_at": published_at.isoformat() if published_at else None,
                }
            )
    return items


def fetch_rss(sources, interests):
    items = []
    for feed_cfg in sources.get("rss_feeds", []):
        url = feed_cfg["url"]
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:
            print(f"  [warn] RSS feed failed: {feed_cfg.get('label', url)}: {exc}")
            continue

        for entry in parsed.entries[:10]:
            title = entry.get("title", "")
            description = entry.get("summary", "")
            if RUMOR_PATTERN.search(f"{title} {description}"):
                continue
            published_at = parse_rss_date(entry)
            if not is_recent(published_at):
                continue
            matched = match_interests(f"{title} {description}", interests)
            # RSS feeds are hand-picked per category, so tag them with their
            # configured category even if the keyword match misses (e.g. a
            # Raptors Republic headline that never says the word "Raptors").
            if feed_cfg["category"] not in matched:
                matched.append(feed_cfg["category"])
            items.append(
                {
                    "title": title,
                    "description": description,
                    "url": entry.get("link"),
                    "source": feed_cfg.get("label", url),
                    "feed_category": feed_cfg["category"],
                    "matched_interests": matched,
                    "published_at": published_at.isoformat() if published_at else None,
                }
            )
    return items


def quote_twelvedata(sources, symbol):
    if not TWELVEDATA_API_KEY:
        print("  [skip] TWELVEDATA_API_KEY not set")
        return {"symbol": symbol, "close": None, "percent_change": None}
    try:
        resp = requests.get(
            f"{sources['apis']['twelvedata']['base_url']}/quote",
            params={"symbol": symbol, "apikey": TWELVEDATA_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": symbol,
            "close": data.get("close"),
            "percent_change": data.get("percent_change"),
        }
    except requests.RequestException as exc:
        print(f"  [warn] Twelve Data quote failed for {symbol}: {exc}")
        return {"symbol": symbol, "close": None, "percent_change": None}


def quote_yfinance(symbol):
    try:
        info = yfinance.Ticker(symbol).fast_info
        last = info.get("lastPrice")
        prev = info.get("previousClose")
        percent_change = ((last - prev) / prev * 100) if last and prev else None
        return {"symbol": symbol, "close": last, "percent_change": percent_change}
    except Exception as exc:
        print(f"  [warn] yfinance quote failed for {symbol}: {exc}")
        return {"symbol": symbol, "close": None, "percent_change": None}


def is_non_us_symbol(symbol):
    # Twelve Data's free tier only covers US-listed symbols (see sources.yaml
    # comment) — route anything with an exchange suffix (e.g. "SHOP.TO") or a
    # Yahoo-style index prefix ("^GSPTSE") to yfinance instead.
    return "." in symbol or symbol.startswith("^")


def fetch_market(sources, tickers):
    indices = []
    for idx in sources["apis"]["twelvedata"]["indices"]:
        provider = idx.get("provider", "twelvedata")
        quote = quote_yfinance(idx["symbol"]) if provider == "yfinance" else quote_twelvedata(sources, idx["symbol"])
        indices.append({**quote, "label": idx["label"]})

    ticker_quotes = [
        quote_yfinance(t) if is_non_us_symbol(t) else quote_twelvedata(sources, t)
        for t in tickers
    ]
    return {"indices": indices, "tickers": ticker_quotes}


def main():
    print("Loading config...")
    interests, sources, tickers = load_config()

    print("Fetching Currents API headlines...")
    currents_items = fetch_currents(sources, interests)
    print(f"  got {len(currents_items)} items")

    print("Fetching RSS feeds...")
    rss_items = fetch_rss(sources, interests)
    print(f"  got {len(rss_items)} items")

    print("Fetching market data...")
    market = fetch_market(sources, tickers)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headlines": currents_items + rss_items,
        "market": market,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "latest.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {len(output['headlines'])} headlines + market data to {out_path}")


if __name__ == "__main__":
    main()
