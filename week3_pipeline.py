"""Week 3 audit infrastructure and safe HTTP collection. No future outcome inference."""
import argparse
import csv
import hashlib
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from common import get_db, now_ts
from week2_spec import install as install_week2

SCHEMA = """
CREATE TABLE IF NOT EXISTS w3_runs (
 run_id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, started_at INTEGER NOT NULL,
 finished_at INTEGER, status TEXT NOT NULL, parameters_json TEXT NOT NULL,
 error TEXT);
CREATE TABLE IF NOT EXISTS w3_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, api TEXT NOT NULL,
 endpoint TEXT NOT NULL, params_json TEXT NOT NULL, fetched_at INTEGER NOT NULL,
 http_status INTEGER, response_sha256 TEXT, response_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS w3_errors (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, stage TEXT NOT NULL,
 identifier TEXT, occurred_at INTEGER NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS w3_windows (
 token_id TEXT NOT NULL, start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
 fidelity INTEGER NOT NULL, fetched_at INTEGER NOT NULL, n_points INTEGER NOT NULL,
 status TEXT NOT NULL, PRIMARY KEY(token_id,start_ts,end_ts,fidelity));
CREATE TABLE IF NOT EXISTS w3_trade_pages (
 condition_id TEXT NOT NULL, offset INTEGER NOT NULL, fetched_at INTEGER NOT NULL,
 n_rows INTEGER NOT NULL, status TEXT NOT NULL,
 PRIMARY KEY(condition_id,offset));
CREATE TABLE IF NOT EXISTS w3_price_provenance (
 token_id TEXT NOT NULL, ts INTEGER NOT NULL, fetched_at INTEGER NOT NULL,
 source TEXT NOT NULL, PRIMARY KEY(token_id,ts));
CREATE TABLE IF NOT EXISTS w3_snapshots (
 market_id TEXT NOT NULL, ts INTEGER NOT NULL, raw_json TEXT NOT NULL,
 PRIMARY KEY(market_id,ts));
CREATE INDEX IF NOT EXISTS idx_w3_requests_run ON w3_requests(run_id);
"""

def install(conn):
    install_week2(conn)
    conn.executescript(SCHEMA)
    conn.commit()

def begin(conn, mode, params):
    install(conn)
    cur = conn.execute('INSERT INTO w3_runs(mode,started_at,status,parameters_json) VALUES(?,?,?,?)',
                       (mode,now_ts(),'running',json.dumps(params,sort_keys=True)))
    conn.commit()
    return cur.lastrowid

def finish(conn, run_id, error=None):
    conn.execute('UPDATE w3_runs SET finished_at=?,status=?,error=? WHERE run_id=?',
                 (now_ts(),'failed' if error else 'completed',str(error) if error else None,run_id))
    conn.commit()

def fail(conn, run_id, stage, identifier, error):
    conn.execute('INSERT INTO w3_errors(run_id,stage,identifier,occurred_at,message) VALUES(?,?,?,?,?)',
                 (run_id,stage,str(identifier) if identifier is not None else None,now_ts(),str(error)))
    conn.commit()

def request(conn, session, url, params=None, run_id=None, pause=0.15, timeout=30):
    """Save immutable request/response (including errors). Avoid committing other callers' partial work."""
    from urllib.parse import urlsplit
    api=urlsplit(url).netloc
    stamp=now_ts()
    status=None; result=None; err=None
    try:
        response=session.get(url,params=params,timeout=timeout)
        status=response.status_code
        response.raise_for_status()
        result=response.json()
        return result
    except Exception as exc:
        err=str(exc)
        raise
    finally:
        raw=json.dumps(result,sort_keys=True,ensure_ascii=False,default=str) if result is not None else None
        digest=hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None
        conn.execute('INSERT INTO w3_requests(run_id,api,endpoint,params_json,fetched_at,http_status,response_sha256,response_json,error) VALUES(?,?,?,?,?,?,?,?,?)',
                     (run_id,api,url,json.dumps(params or {},sort_keys=True),stamp,status,digest,raw,err))
        conn.commit()
        if pause: time.sleep(pause)

def validate_history(history, token, lo, hi):
    if not isinstance(history,dict) or not isinstance(history.get('history'),list):
        raise ValueError('Malformed CLOB history response')
    rows=[]
    for point in history['history']:
        ts=int(point['t']); p=float(point['p'])
        if not math.isfinite(p) or not 0 <= p <= 1 or not lo <= ts <= hi:
            raise ValueError(f'Invalid price or timestamp: token={token} point={point}')
        rows.append((token,ts,p))
    return rows

def coverage(conn, out=None):
    install(conn)
    results={}
    for key, sql in {
        'markets':'SELECT COUNT(*) FROM markets',
        'markets_with_tokens':'SELECT COUNT(*) FROM markets WHERE token_yes IS NOT NULL AND token_no IS NOT NULL',
        'independently_verified_markets':'SELECT COUNT(*) FROM w2_resolution_checks WHERE verified_outcome IN (0,1) AND verified_source IS NOT NULL AND rules_archived=1',
        'price_points':'SELECT COUNT(*) FROM price_history',
        'markets_with_yes_history':'SELECT COUNT(DISTINCT m.market_id) FROM markets m JOIN price_history p ON m.token_yes=p.token_id',
        'trade_rows':'SELECT COUNT(*) FROM trades',
        'snapshot_rows':'SELECT COUNT(*) FROM market_snapshots',
        'successful_price_windows':"SELECT COUNT(*) FROM w3_windows WHERE status='ok'",
        'failed_price_windows':"SELECT COUNT(*) FROM w3_windows WHERE status='failed'",
        'collection_errors':'SELECT COUNT(*) FROM w3_errors',
        'requests':'SELECT COUNT(*) FROM w3_requests',
    }.items(): results[key]=conn.execute(sql).fetchone()[0]
    times=conn.execute('SELECT MIN(ts),MAX(ts) FROM price_history').fetchone()
    results['first_price_ts'],results['last_price_ts']=times
    if out:
        Path(out).write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
    return results

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',default='polymarket_fyp.db')
    ap.add_argument('--out',default='week3_coverage.json')
    args=ap.parse_args()
    conn=get_db(args.db)
    print(json.dumps(coverage(conn,args.out),indent=2))

if __name__=='__main__':main()
