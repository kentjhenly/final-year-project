"""Timestamped news via the GDELT DOC 2.0 API (free, no key).
IMPORTANT: the DOC API only searches roughly the most recent 3 months, so historical
back-tests must use markets that ended within ~85 days (or collect prospectively).
GDELT asks for <= 1 request / 5 s. 'seendate' (when GDELT first saw the article) is stored as
published_ts: it is the conservative time at which the article was available.
"""
import argparse
import logging
import time
from datetime import datetime, timezone

from common import get_db, make_session, keywords, now_ts, log

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"


def _fmt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d%H%M%S")


def _parse_seen(s):
    try:
        return int(datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp())
    except (ValueError, TypeError):
        return None


def collect_news(conn, s, lookback_days, window_days, max_markets):
    cutoff_oldest = now_ts() - 88 * 86400
    rows = conn.execute("""SELECT market_id, question, COALESCE(closed_ts, end_ts) FROM markets
        WHERE outcome IS NOT NULL AND market_id NOT IN (SELECT DISTINCT market_id FROM news)
        ORDER BY volume DESC""").fetchall()
    done = 0
    for mid, question, end in rows:
        if done >= max_markets:
            break
        if not end or end - lookback_days * 86400 < cutoff_oldest:
            continue  # outside GDELT's rolling window
        query = " ".join(keywords(question)) + " sourcelang:english"
        t, n = end - lookback_days * 86400, 0
        while t < end:
            t2 = min(t + window_days * 86400, end)
            params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": 250,
                      "sort": "datedesc", "startdatetime": _fmt(t), "enddatetime": _fmt(t2)}
            try:
                r = s.get(GDELT, params=params, timeout=45)
                data = r.json()
            except Exception as e:  # GDELT returns plain text on errors / rate limits
                log.warning("GDELT failed for market %s: %s", mid, e)
                time.sleep(10)
                t = t2
                continue
            arts = data.get("articles", []) or []
            conn.executemany("INSERT OR IGNORE INTO news VALUES (?,?,?,?,?,?,?,?,?)", [
                (mid, a.get("url"), a.get("title"), a.get("domain"), a.get("language"),
                 a.get("sourcecountry"), _parse_seen(a.get("seendate")), query, now_ts())
                for a in arts if a.get("url")])
            n += len(arts)
            t = t2
            time.sleep(5.5)
        conn.commit()
        done += 1
        log.info("market %s: %d articles (query=%r)", mid, n, query)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="polymarket_fyp.db")
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--max-markets", type=int, default=300)
    a = ap.parse_args()
    collect_news(get_db(a.db), make_session(), a.lookback_days, a.window_days, a.max_markets)
