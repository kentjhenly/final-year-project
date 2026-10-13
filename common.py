"""Shared helpers: SQLite schema, HTTP session with retries, timestamp utils.
Requires Python >= 3.11 (datetime.fromisoformat handles most ISO variants).
All timestamps are stored as UTC unix seconds (INTEGER)."""
import re
import sqlite3
import time
import logging
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DB_PATH = "polymarket_fyp.db"
log = logging.getLogger("fyp")

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    condition_id TEXT,
    slug TEXT,
    event_slug TEXT,
    question TEXT,
    description TEXT,
    resolution_source TEXT,
    category TEXT,
    token_yes TEXT,
    token_no TEXT,
    start_ts INTEGER,
    end_ts INTEGER,
    closed_ts INTEGER,
    volume REAL,
    liquidity REAL,
    outcome INTEGER,          -- 1 = YES won, 0 = NO won, NULL = unresolved/void
    uma_status TEXT,
    raw_json TEXT,
    fetched_at INTEGER        -- when WE downloaded it (audit trail)
);
CREATE TABLE IF NOT EXISTS price_history (
    token_id TEXT, ts INTEGER, price REAL,
    PRIMARY KEY (token_id, ts)
);
CREATE TABLE IF NOT EXISTS market_snapshots (   -- prospective (live) collection
    market_id TEXT, ts INTEGER, yes_price REAL, volume REAL, liquidity REAL,
    PRIMARY KEY (market_id, ts)
);
CREATE TABLE IF NOT EXISTS trades (
    condition_id TEXT, ts INTEGER, side TEXT, outcome_index INTEGER,
    price REAL, size REAL, tx_hash TEXT, asset TEXT,
    UNIQUE (tx_hash, asset, side, price, size, ts)
);
CREATE TABLE IF NOT EXISTS news (
    market_id TEXT, url TEXT, title TEXT, domain TEXT, language TEXT,
    country TEXT,
    published_ts INTEGER,     -- GDELT 'seendate' = when GDELT first saw it (safe availability time)
    query TEXT, fetched_at INTEGER,
    PRIMARY KEY (market_id, url)
);
CREATE TABLE IF NOT EXISTS social_posts (
    market_id TEXT, post_id TEXT, source TEXT, created_ts INTEGER,
    title TEXT, text TEXT, score INTEGER, num_comments INTEGER,
    subreddit TEXT, fetched_at INTEGER,
    PRIMARY KEY (market_id, post_id)
);
CREATE TABLE IF NOT EXISTS financial_series (
    symbol TEXT, ts INTEGER,  -- daily bar date 00:00 UTC; close is only known at ts + 86400
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_news_ts ON news (market_id, published_ts);
CREATE INDEX IF NOT EXISTS idx_social_ts ON social_posts (market_id, created_ts);
"""


def get_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def now_ts() -> int:
    return int(time.time())


def iso_to_ts(s):
    """Parse '2024-11-05T00:00:00Z' / '2024-11-06 12:00:00+00' etc. -> unix seconds (UTC)."""
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T")
    if re.search(r"[+-]\d{2}$", s):
        s += ":00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=1.5,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "cuhk-fyp-hx2605-research/0.1"
    return s


def get_json(session, url, params=None, pause=0.15, timeout=30):
    r = session.get(url, params=params, timeout=timeout)
    time.sleep(pause)
    r.raise_for_status()
    return r.json()


def keywords(question: str, n: int = 4):
    """Crude keyword extraction from a market question (tune this for better recall/precision)."""
    stop = set("""will the a an of in on at by for to be is are was were before after during
    than then over under above below between from with without or and not no yes win wins won
    does do did has have had get gets reach hit exceed announce announced say says
    january february march april may june july august september october november december
    2020 2021 2022 2023 2024 2025 2026 2027 end any least more less most new""".split())
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*", question or "")
    kws = [w.strip(".'-") for w in words if w.lower() not in stop and len(w) > 2]
    caps = [w for w in kws if w[0].isupper() or w.isdigit()]
    return (caps or kws)[:n]
