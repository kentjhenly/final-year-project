"""Week 2 market audit and point-in-time data specification.

Run: python week2_spec.py --db polymarket_fyp.db --out week2_selection.csv
Never promotes a price-inferred label into a verified outcome.
"""
import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from common import get_db, now_ts

MIGRATION = """
CREATE TABLE IF NOT EXISTS w2_raw_requests (
 id INTEGER PRIMARY KEY, api TEXT NOT NULL, endpoint TEXT NOT NULL,
 params_json TEXT NOT NULL, fetched_at INTEGER NOT NULL,
 http_status INTEGER, response_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS w2_selection (
 market_id TEXT PRIMARY KEY, event_group TEXT NOT NULL,
 provisional INTEGER NOT NULL CHECK(provisional IN (0,1)),
 verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
 reason TEXT NOT NULL, reviewed_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS w2_resolution_checks (
 market_id TEXT PRIMARY KEY, verified_outcome INTEGER CHECK(verified_outcome IN (0,1)),
 verified_resolution_ts INTEGER, information_cutoff_ts INTEGER,
 verified_source TEXT, rules_archived INTEGER NOT NULL DEFAULT 0,
 checked_at INTEGER NOT NULL,
 FOREIGN KEY (market_id) REFERENCES markets(market_id));
CREATE TABLE IF NOT EXISTS w2_price_coverage (
 market_id TEXT, horizon_days INTEGER, cutoff_ts INTEGER,
 selected_price_ts INTEGER, selected_price REAL,
 status TEXT NOT NULL, checked_at INTEGER NOT NULL,
 PRIMARY KEY (market_id,horizon_days));
CREATE INDEX IF NOT EXISTS idx_w2_raw_api ON w2_raw_requests(api,fetched_at);
"""

def install(conn):
    conn.executescript(MIGRATION)
    conn.commit()

def _array(value):
    if isinstance(value,list): return value
    if isinstance(value,str):
        try:
            v=json.loads(value)
            return v if isinstance(v,list) else []
        except (ValueError,TypeError): pass
    return []

def selection(m):
    """Provisional only: archived rules and externally verified labels are separate."""
    raw=json.loads(m['raw_json']) if isinstance(m['raw_json'],str) else m['raw_json']
    outcomes=_array(raw.get('outcomes'))
    tokens=_array(raw.get('clobTokenIds'))
    reasons=[]
    if [str(x).casefold() for x in outcomes]!=['yes','no']: reasons.append('not_binary_yes_no')
    if len(tokens)!=2 or not all(str(t).strip() for t in tokens): reasons.append('missing_tokens')
    if not m['question']: reasons.append('missing_question')
    if m['end_ts'] is None: reasons.append('missing_end_date')
    if m['closed_ts'] is None: reasons.append('missing_closed_time')
    if not m['resolution_source']: reasons.append('missing_resolution_source')
    return not reasons, ';'.join(reasons) or 'provisional_only_requires_verification'

def audit_markets(conn,horizons=(1,3,7),stale_hours=24):
    install(conn)
    conn.row_factory=sqlite3.Row
    markets=conn.execute('SELECT * FROM markets ORDER BY market_id').fetchall()
    now=now_ts()
    for m in markets:
        valid,reason=selection(m)
        group=m['event_slug'] or m['condition_id'] or m['market_id']
        check=conn.execute('SELECT * FROM w2_resolution_checks WHERE market_id=?',(m['market_id'],)).fetchone()
        verified=bool(valid and check and check['verified_outcome'] in (0,1)
                      and check['verified_resolution_ts'] is not None
                      and check['information_cutoff_ts'] is not None
                      and check['information_cutoff_ts'] <= check['verified_resolution_ts']
                      and check['verified_source'] and check['rules_archived'])
        conn.execute('INSERT INTO w2_selection VALUES(?,?,?,?,?,?) ON CONFLICT(market_id) DO UPDATE SET event_group=excluded.event_group, provisional=excluded.provisional, verified=excluded.verified, reason=excluded.reason, reviewed_at=excluded.reviewed_at',
                     (m['market_id'],group,int(valid),int(verified),reason if not verified else 'verified',now))
        for h in horizons:
            cutoff=(check['information_cutoff_ts']-h*86400) if verified else None
            status='requires_verified_resolution_and_historical_rules'
            price_ts=price=None
            if cutoff is not None:
                row=conn.execute('SELECT ts,price FROM price_history WHERE token_id=? AND ts<=? ORDER BY ts DESC LIMIT 1',(m['token_yes'],cutoff)).fetchone()
                if row is None: status='missing_history'
                elif cutoff-row['ts']>stale_hours*3600: status='stale_history'
                elif not 0<=row['price']<=1: status='invalid_price'
                elif m['start_ts'] is not None and cutoff<m['start_ts']: status='pre_market_start'
                else:
                    status='eligible';price_ts=row['ts'];price=row['price']
            conn.execute('INSERT INTO w2_price_coverage VALUES(?,?,?,?,?,?,?) ON CONFLICT(market_id,horizon_days) DO UPDATE SET cutoff_ts=excluded.cutoff_ts,selected_price_ts=excluded.selected_price_ts,selected_price=excluded.selected_price,status=excluded.status,checked_at=excluded.checked_at',
                         (m['market_id'],h,cutoff,price_ts,price,status,now))
    conn.commit()
    return len(markets)

def verify_resolution(conn,market_id,outcome,resolution_ts,information_cutoff_ts,source,rules_archived):
    """Manual verification entrypoint; caller must inspect independent resolution source/archived rules.
    A final Gamma price alone is NOT independent verification.
    """
    install(conn)
    if outcome not in (0,1) or not source or not rules_archived or not (0<information_cutoff_ts<=resolution_ts):
        raise ValueError('Independent verification source, archived rules, valid outcome and timing required')
    if not conn.execute('SELECT 1 FROM markets WHERE market_id=?',(market_id,)).fetchone():
        raise ValueError('unknown market')
    conn.execute('INSERT INTO w2_resolution_checks VALUES(?,?,?,?,?,?,?) ON CONFLICT(market_id) DO UPDATE SET verified_outcome=excluded.verified_outcome,verified_resolution_ts=excluded.verified_resolution_ts,information_cutoff_ts=excluded.information_cutoff_ts,verified_source=excluded.verified_source,rules_archived=excluded.rules_archived,checked_at=excluded.checked_at',
                 (market_id,outcome,resolution_ts,information_cutoff_ts,source,1,now_ts()))
    conn.commit()

def export(conn,out):
    conn.row_factory=sqlite3.Row
    rows=conn.execute('''SELECT s.market_id,s.event_group,s.provisional,s.verified,s.reason,
      p.horizon_days,p.cutoff_ts,p.selected_price_ts,p.selected_price,p.status
      FROM w2_selection s LEFT JOIN w2_price_coverage p USING(market_id)
      ORDER BY s.market_id,p.horizon_days''').fetchall()
    columns=['market_id','event_group','provisional','verified','reason','horizon_days','cutoff_ts','selected_price_ts','selected_price','status']
    with open(out,'w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(dict(r) for r in rows)
    return len(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',default='polymarket_fyp.db')
    ap.add_argument('--out',default='week2_selection.csv')
    ap.add_argument('--horizons',type=int,nargs='+',default=[1,3,7])
    ap.add_argument('--stale-hours',type=int,default=24)
    args=ap.parse_args()
    if not args.horizons or any(h<=0 for h in args.horizons) or args.stale_hours<=0: ap.error('positive horizons and stale-hours required')
    conn=get_db(args.db)
    n=audit_markets(conn,args.horizons,args.stale_hours)
    exported=export(conn,args.out)
    print(f'Inspected {n} markets; exported {exported} horizon audit rows to {args.out}. Verified status requires independent evidence.')
if __name__=='__main__': main()
