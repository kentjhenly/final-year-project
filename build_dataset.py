"""Builds the leakage-safe research dataset (one row per market x prediction horizon).

For each resolved market and horizon h, the forecast time is T = resolve_ts - h days.
EVERY feature uses only data with timestamp <= T. Label = final outcome (1 = YES).
Train/test split is temporal (by resolution time), never random.

  python build_dataset.py --horizons 1 3 7 14 --out research_dataset.csv
"""
import argparse

import numpy as np
import pandas as pd

from common import get_db

DAY = 86400


def _count_between(arr, lo, hi):
    """count of sorted timestamps in (lo, hi]"""
    return int(np.searchsorted(arr, hi, side="right") - np.searchsorted(arr, lo, side="right"))


def build(db, horizons, out, stale_hours, test_frac, window_days):
    conn = get_db(db)
    markets = pd.read_sql("SELECT * FROM markets WHERE outcome IS NOT NULL", conn)
    prices = pd.read_sql("SELECT token_id, ts, price FROM price_history ORDER BY ts", conn)
    price_by_token = {k: g[["ts", "price"]].to_numpy() for k, g in prices.groupby("token_id")}
    news_ts = {k: np.sort(g["published_ts"].dropna().to_numpy())
               for k, g in pd.read_sql("SELECT market_id, published_ts FROM news", conn).groupby("market_id")}
    soc_ts = {k: np.sort(g["created_ts"].dropna().to_numpy())
              for k, g in pd.read_sql("SELECT market_id, created_ts FROM social_posts", conn).groupby("market_id")}
    fin = {k: g[["ts", "close"]].to_numpy()
           for k, g in pd.read_sql("SELECT symbol, ts, close FROM financial_series ORDER BY ts", conn).groupby("symbol")}

    rows = []
    for m in markets.itertuples():
        resolve_ts = m.closed_ts if pd.notna(m.closed_ts) else m.end_ts
        arr = price_by_token.get(m.token_yes)
        if arr is None or pd.isna(resolve_ts):
            continue
        for h in horizons:
            T = int(resolve_ts - h * DAY)
            if pd.notna(m.start_ts) and T < m.start_ts:
                continue
            hist = arr[arr[:, 0] <= T]
            if len(hist) == 0 or T - hist[-1, 0] > stale_hours * 3600:
                continue  # no recent market price at T
            p_now = hist[-1, 1]
            old = hist[hist[:, 0] <= T - DAY]
            win = hist[hist[:, 0] > T - window_days * DAY]
            row = {
                "market_id": m.market_id, "question": m.question, "category": m.category,
                "horizon_days": h, "forecast_ts": T, "resolve_ts": int(resolve_ts),
                "market_price": p_now,
                "price_change_24h": p_now - old[-1, 1] if len(old) else np.nan,
                f"price_vol_{window_days}d": float(np.std(win[:, 1])) if len(win) > 2 else np.nan,
                "n_price_points": len(win),
                "news_count": _count_between(news_ts.get(m.market_id, np.array([])), T - window_days * DAY, T),
                "social_count": _count_between(soc_ts.get(m.market_id, np.array([])), T - window_days * DAY, T),
                "outcome": int(m.outcome),
            }
            for sym, a in fin.items():
                a_ok = a[a[:, 0] + DAY <= T]  # daily close only known one day after bar date
                prev = a_ok[a_ok[:, 0] <= T - window_days * DAY]
                row[f"ret_{window_days}d_{sym}"] = (a_ok[-1, 1] / prev[-1, 1] - 1) if len(a_ok) and len(prev) else np.nan
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No rows built - collect markets and prices first.")
        return
    cut = df["resolve_ts"].quantile(1 - test_frac)
    df["split"] = np.where(df["resolve_ts"] <= cut, "train", "test")
    df["extreme_price_flag"] = ((df.market_price >= 0.97) | (df.market_price <= 0.03)).astype(int)
    df.to_csv(out, index=False)
    print(f"{len(df)} rows, {df.market_id.nunique()} markets -> {out}")
    print(df.groupby(["horizon_days", "split"]).size())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="polymarket_fyp.db")
    ap.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 7, 14])
    ap.add_argument("--out", default="research_dataset.csv")
    ap.add_argument("--stale-hours", type=int, default=24)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--window-days", type=int, default=7)
    a = ap.parse_args()
    build(a.db, a.horizons, a.out, a.stale_hours, a.test_frac, a.window_days)
