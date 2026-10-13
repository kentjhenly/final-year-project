"""Polymarket collector (Gamma = metadata, CLOB = price history, Data API = trades).

Usage examples:
  python collect_polymarket.py markets   --days-back 85 --min-volume 50000 --max-markets 500
  python collect_polymarket.py prices    --fidelity 60
  python collect_polymarket.py trades    --max-per-market 5000      # optional
  python collect_polymarket.py snapshot  --min-volume 100000        # run daily/hourly (cron) for prospective data
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

from common import (get_db, make_session, get_json, iso_to_ts, now_ts, log)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"


def _j(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except ValueError:
            return None
    return x


def parse_market(m, require_resolved=True):
    outcomes = _j(m.get("outcomes"))
    prices = _j(m.get("outcomePrices"))
    tokens = _j(m.get("clobTokenIds"))
    if not outcomes or [str(o).lower() for o in outcomes] != ["yes", "no"]:
        return None  # keep binary Yes/No markets only
    if not tokens or len(tokens) != 2:
        return None
    outcome = None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
        if p0 >= 0.99 and p1 <= 0.01:
            outcome = 1
        elif p1 >= 0.99 and p0 <= 0.01:
            outcome = 0
    except (TypeError, ValueError, IndexError):
        pass
    if require_resolved and outcome is None:
        return None  # drop unresolved / 50-50 voided markets
    ev = (m.get("events") or [{}])[0]
    return {
        "market_id": str(m.get("id")),
        "condition_id": m.get("conditionId"),
        "slug": m.get("slug"),
        "event_slug": ev.get("slug"),
        "question": m.get("question"),
        "description": m.get("description"),
        "resolution_source": m.get("resolutionSource"),
        "category": m.get("category"),
        "token_yes": tokens[0],
        "token_no": tokens[1],
        "start_ts": iso_to_ts(m.get("startDate")),
        "end_ts": iso_to_ts(m.get("endDate")),
        "closed_ts": iso_to_ts(m.get("closedTime")),
        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
        "liquidity": float(m.get("liquidityNum") or m.get("liquidity") or 0),
        "outcome": outcome,
        "uma_status": m.get("umaResolutionStatus"),
        "raw_json": json.dumps(m),
        "fetched_at": now_ts(),
    }


UPSERT = """INSERT OR REPLACE INTO markets VALUES (:market_id,:condition_id,:slug,:event_slug,
:question,:description,:resolution_source,:category,:token_yes,:token_no,:start_ts,:end_ts,
:closed_ts,:volume,:liquidity,:outcome,:uma_status,:raw_json,:fetched_at)"""


def collect_markets(conn, s, days_back, min_volume, max_markets):
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    offset, kept = 0, 0
    while kept < max_markets:
        params = {"closed": "true", "limit": 100, "offset": offset,
                  "end_date_min": (now - timedelta(days=days_back)).strftime(fmt),
                  "end_date_max": now.strftime(fmt),
                  "volume_num_min": min_volume,
                  "order": "volumeNum", "ascending": "false"}
        batch = get_json(s, f"{GAMMA}/markets", params)
        if not batch:
            break
        for m in batch:
            row = parse_market(m, require_resolved=True)
            if row:
                conn.execute(UPSERT, row)
                kept += 1
        conn.commit()
        offset += len(batch)
        log.info("scanned %d markets, kept %d resolved binary markets", offset, kept)


def collect_prices(conn, s, fidelity, chunk_days, pre_days):
    """YES-token price series. NO price ~= 1 - YES. Chunked by time window because the CLOB
    endpoint can return empty results for long ranges on closed markets."""
    rows = conn.execute("""SELECT market_id, token_yes, start_ts, end_ts, closed_ts FROM markets
        WHERE outcome IS NOT NULL AND token_yes NOT IN (SELECT DISTINCT token_id FROM price_history)""").fetchall()
    for i, (mid, token, start_ts, end_ts, closed_ts) in enumerate(rows, 1):
        end = closed_ts or end_ts
        if not end:
            continue
        t = max(start_ts or 0, end - pre_days * 86400)
        n = 0
        try:
            while t < end:
                t2 = min(t + chunk_days * 86400, end)
                data = get_json(s, f"{CLOB}/prices-history",
                                {"market": token, "startTs": t, "endTs": t2, "fidelity": fidelity})
                hist = data.get("history", [])
                conn.executemany("INSERT OR IGNORE INTO price_history VALUES (?,?,?)",
                                 [(token, int(h["t"]), float(h["p"])) for h in hist])
                n += len(hist)
                t = t2
            conn.commit()
            log.info("[%d/%d] market %s: %d price points", i, len(rows), mid, n)
        except Exception as e:  # keep going on per-market failures
            log.warning("prices failed for market %s: %s", mid, e)


def collect_trades(conn, s, max_per_market):
    rows = conn.execute("""SELECT market_id, condition_id FROM markets WHERE outcome IS NOT NULL
        AND condition_id NOT IN (SELECT DISTINCT condition_id FROM trades)""").fetchall()
    for i, (mid, cond) in enumerate(rows, 1):
        offset, n = 0, 0
        try:
            while offset < max_per_market:
                batch = get_json(s, f"{DATA}/trades", {"market": cond, "limit": 500, "offset": offset})
                if not batch:
                    break
                conn.executemany("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?)", [
                    (cond, int(t["timestamp"]), t.get("side"), t.get("outcomeIndex"),
                     float(t["price"]), float(t["size"]), t.get("transactionHash"), t.get("asset"))
                    for t in batch])
                n += len(batch)
                offset += len(batch)
            conn.commit()
            log.info("[%d/%d] market %s: %d trades", i, len(rows), mid, n)
        except Exception as e:  # the API caps offset depth; partial data is expected on huge markets
            log.warning("trades failed for market %s at offset %d: %s", mid, offset, e)


def snapshot_open(conn, s, min_volume, max_markets):
    """Prospective collection: record live prices of open markets with OUR OWN timestamp.
    Run on a schedule; this gives leakage-free evaluation data for markets that resolve later."""
    ts, offset, kept = now_ts(), 0, 0
    while kept < max_markets:
        batch = get_json(s, f"{GAMMA}/markets", {"active": "true", "closed": "false", "limit": 100,
                         "offset": offset, "volume_num_min": min_volume,
                         "order": "volumeNum", "ascending": "false"})
        if not batch:
            break
        for m in batch:
            row = parse_market(m, require_resolved=False)
            if not row:
                continue
            conn.execute(UPSERT, row)
            try:
                yes_price = float(_j(m.get("outcomePrices"))[0])
            except (TypeError, ValueError, IndexError):
                continue
            conn.execute("INSERT OR IGNORE INTO market_snapshots VALUES (?,?,?,?,?)",
                         (row["market_id"], ts, yes_price, row["volume"], row["liquidity"]))
            kept += 1
        conn.commit()
        offset += len(batch)
    log.info("snapshotted %d open markets at ts=%d", kept, ts)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["markets", "prices", "trades", "snapshot"])
    ap.add_argument("--db", default="polymarket_fyp.db")
    ap.add_argument("--days-back", type=int, default=85, help="markets that ended within this many days")
    ap.add_argument("--min-volume", type=float, default=50000)
    ap.add_argument("--max-markets", type=int, default=500)
    ap.add_argument("--fidelity", type=int, default=60, help="price resolution in minutes")
    ap.add_argument("--chunk-days", type=int, default=14)
    ap.add_argument("--pre-days", type=int, default=90, help="price history window before resolution")
    ap.add_argument("--max-per-market", type=int, default=5000)
    a = ap.parse_args()
    conn, sess = get_db(a.db), make_session()
    if a.mode == "markets":
        collect_markets(conn, sess, a.days_back, a.min_volume, a.max_markets)
    elif a.mode == "prices":
        collect_prices(conn, sess, a.fidelity, a.chunk_days, a.pre_days)
    elif a.mode == "trades":
        collect_trades(conn, sess, a.max_per_market)
    else:
        snapshot_open(conn, sess, a.min_volume, a.max_markets)
