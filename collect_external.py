"""Financial-market data (yfinance) and social-media signal (Reddit archive).

  python collect_external.py financial
  python collect_external.py social --lookback-days 30

NOTE: the social endpoint (Arctic Shift, a public Reddit archive) is UNTESTED here - verify its
current parameters at https://github.com/ArthurHeitmann/arctic_shift before relying on it.
X/Twitter has no free historical API; swap in another source in fetch_social() if you have one.
"""
import argparse
import logging
import time

import pandas as pd

from common import get_db, make_session, keywords, now_ts, log

SYMBOLS = ["^GSPC", "^IXIC", "^VIX", "^TNX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD", "ETH-USD"]
ARCTIC = "https://arctic-shift.photon-lab.com/api/posts/search"


def collect_financial(conn, symbols=SYMBOLS):
    import yfinance as yf
    lo, hi = conn.execute("SELECT MIN(start_ts), MAX(COALESCE(closed_ts, end_ts)) FROM markets").fetchone()
    start = pd.to_datetime((lo or now_ts() - 120 * 86400) - 60 * 86400, unit="s").strftime("%Y-%m-%d")
    end = pd.to_datetime((hi or now_ts()) + 2 * 86400, unit="s").strftime("%Y-%m-%d")
    for sym in symbols:
        try:
            df = yf.download(sym, start=start, end=end, interval="1d", auto_adjust=False, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            rows = [(sym, int(pd.Timestamp(idx).tz_localize("UTC").timestamp()),
                     float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]),
                     float(r.get("Volume", 0) or 0)) for idx, r in df.iterrows()]
            conn.executemany("INSERT OR REPLACE INTO financial_series VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
            log.info("%s: %d daily bars", sym, len(rows))
        except Exception as e:
            log.warning("yfinance failed for %s: %s", sym, e)


def fetch_social(s, query, after, before):
    r = s.get(ARCTIC, params={"query": query, "after": after, "before": before,
                              "limit": 100, "sort": "desc"}, timeout=45)
    r.raise_for_status()
    return r.json().get("data", [])


def collect_social(conn, s, lookback_days, max_markets):
    rows = conn.execute("""SELECT market_id, question, COALESCE(closed_ts, end_ts) FROM markets
        WHERE outcome IS NOT NULL AND market_id NOT IN (SELECT DISTINCT market_id FROM social_posts)
        ORDER BY volume DESC LIMIT ?""", (max_markets,)).fetchall()
    for mid, question, end in rows:
        if not end:
            continue
        q = " ".join(keywords(question))
        try:
            posts = fetch_social(s, q, end - lookback_days * 86400, end)
        except Exception as e:
            log.warning("social failed for market %s: %s", mid, e)
            continue
        conn.executemany("INSERT OR IGNORE INTO social_posts VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (mid, p.get("id"), "reddit", int(p.get("created_utc", 0)), p.get("title"),
             (p.get("selftext") or "")[:2000], p.get("score"), p.get("num_comments"),
             p.get("subreddit"), now_ts()) for p in posts])
        conn.commit()
        log.info("market %s: %d reddit posts", mid, len(posts))
        time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["financial", "social"])
    ap.add_argument("--db", default="polymarket_fyp.db")
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--max-markets", type=int, default=300)
    a = ap.parse_args()
    conn = get_db(a.db)
    if a.mode == "financial":
        collect_financial(conn)
    else:
        collect_social(conn, make_session(), a.lookback_days, a.max_markets)
