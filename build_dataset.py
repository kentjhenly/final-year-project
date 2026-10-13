"""Week 4: point-in-time research dataset builder for the existing FYP SQLite schema.

Strict mode requires an on-time market snapshot establishing the deadline and
question as they were known at prediction time. Retrospective mode is explicitly
EXPLORATORY and must not be used for leakage-safe performance claims.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from common import get_db, iso_to_ts
from week2_spec import install as install_week2

DAY = 86400


def _deadline(raw):
    """Return deadline from historically observed Gamma payload, if parseable."""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    for k in ('endDate', 'end_date', 'endDateIso'):
        value = obj.get(k)
        if value:
            return iso_to_ts(value)
    return None


def _ordered_splits(groups, train_frac, val_frac, embargo_seconds):
    """Chronological group splits purged by outcome availability and embargo.

    A group stays in exactly one split. Earlier partitions are purged if their
    resolved labels would not yet be available at the next partition's first
    forecast (minus the requested embargo).
    """
    groups = groups.sort_values(['first_forecast', 'event_group'], kind='stable').reset_index(drop=True)
    n = len(groups)
    if n < 3:
        raise ValueError('Need at least three distinct eligible event groups')
    a = max(1, int(n * train_frac))
    b = max(a + 1, int(n * (train_frac + val_frac)))
    if b >= n:
        raise ValueError('Not enough event groups for nonempty train/validation/test')
    groups['split'] = ['train' if i < a else 'validation' if i < b else 'test' for i in range(n)]
    boundaries = {'train': int(groups.loc[b, 'first_forecast']),
                  'validation': int(groups.loc[groups.split.eq('test'), 'first_forecast'].min())}
    # train must precede *validation*, not just test
    boundaries['train'] = int(groups.loc[groups.split.eq('validation'), 'first_forecast'].min())
    removed = []
    for split in ('train', 'validation'):
        invalid = groups.split.eq(split) & (groups.last_resolution + embargo_seconds > boundaries[split])
        removed.extend(groups.loc[invalid, 'event_group'].tolist())
        groups.loc[invalid, 'split'] = 'purged'
    if any(not groups.split.eq(s).any() for s in ('train', 'validation', 'test')):
        raise ValueError('Purging emptied a split; collect more temporally separated events')
    return dict(zip(groups.event_group, groups.split)), removed


def build(db='polymarket_fyp.db', horizons=(1, 3, 7), out='research_dataset.csv',
          stale_hours=24, window_days=7, train_frac=.6, val_frac=.2,
          embargo_hours=0, deadline_policy='strict', allow_late_backfill=False):
    if not horizons or any(int(h) <= 0 for h in horizons) or len(set(horizons)) != len(horizons):
        raise ValueError('Horizons must be distinct positive integer days')
    if stale_hours <= 0 or window_days <= 0 or embargo_hours < 0:
        raise ValueError('Staleness/window must be positive and embargo nonnegative')
    if not 0 < train_frac < 1 or not 0 < val_frac < 1 or train_frac + val_frac >= 1:
        raise ValueError('Invalid split fractions')
    if deadline_policy not in ('strict', 'retrospective'):
        raise ValueError('Unknown deadline policy')
    conn = get_db(db)
    install_week2(conn)
    markets = pd.read_sql_query('''SELECT m.market_id,m.question,m.category,m.token_yes,m.start_ts,
      m.end_ts,m.outcome,m.event_slug,m.condition_id,m.fetched_at,
      s.event_group,s.verified,s.provisional,
      c.verified_outcome,c.verified_resolution_ts,c.information_cutoff_ts,
      c.verified_source,c.rules_archived,c.checked_at
      FROM markets m JOIN w2_selection s ON s.market_id=m.market_id
      JOIN w2_resolution_checks c ON c.market_id=m.market_id
      WHERE s.verified=1 AND s.provisional=1 AND c.rules_archived=1
        AND c.verified_source IS NOT NULL AND c.verified_outcome IN (0,1)
        AND c.verified_resolution_ts IS NOT NULL AND c.information_cutoff_ts IS NOT NULL''', conn)
    prices = pd.read_sql_query('SELECT token_id,ts,price FROM price_history ORDER BY token_id,ts', conn)
    snapshots = pd.read_sql_query('SELECT market_id,ts,raw_json FROM w3_snapshots ORDER BY market_id,ts', conn) if _table_exists(conn, 'w3_snapshots') else pd.DataFrame(columns=['market_id','ts','raw_json'])
    provenance = pd.read_sql_query('SELECT token_id,ts,fetched_at FROM w3_price_provenance',conn) if _table_exists(conn,'w3_price_provenance') else pd.DataFrame(columns=['token_id','ts','fetched_at'])
    news = pd.read_sql_query('SELECT market_id,published_ts,fetched_at,url FROM news',conn)
    social = pd.read_sql_query('SELECT market_id,created_ts,fetched_at,post_id FROM social_posts',conn)
    financial = pd.read_sql_query('SELECT symbol,ts,close FROM financial_series',conn)
    checks = {'input_markets':len(markets),'excluded':{},'deadline_policy':deadline_policy,
              'retrospective_exploratory_only':deadline_policy=='retrospective',
              'allow_late_backfill':bool(allow_late_backfill)}
    def reject(reason):
        checks['excluded'][reason] = checks['excluded'].get(reason,0)+1
    price_groups = {}
    for token, g in prices.groupby('token_id'):
        g = g.loc[pd.to_numeric(g.price,errors='coerce').between(0,1) & pd.to_numeric(g.ts,errors='coerce').notna()].copy()
        g['ts'] = g.ts.astype('int64')
        g = g.drop_duplicates('ts',keep=False).sort_values('ts')
        price_groups[token] = g
    snap_groups = {k:g for k,g in snapshots.groupby('market_id')}
    provenance_map = {(str(r.token_id),int(r.ts)):int(r.fetched_at) for r in provenance.itertuples() if pd.notna(r.fetched_at)}
    news_groups = {k:g for k,g in news.groupby('market_id')}
    social_groups = {k:g for k,g in social.groupby('market_id')}
    fin_groups = {k:g.sort_values('ts') for k,g in financial.groupby('symbol')}
    rows=[]
    for m in markets.itertuples(index=False):
        if m.outcome is not None and pd.notna(m.outcome) and int(m.outcome)!=int(m.verified_outcome):
            reject('conflicting_outcome');continue
        if pd.isna(m.information_cutoff_ts) or pd.isna(m.verified_resolution_ts) or int(m.information_cutoff_ts)>int(m.verified_resolution_ts):
            reject('invalid_resolution_cutoff');continue
        if pd.isna(m.token_yes) or str(m.token_yes) not in price_groups:
            reject('missing_yes_prices');continue
        hist=price_groups[str(m.token_yes)]
        if hist.empty:
            reject('invalid_yes_prices');continue
        group = str(m.event_group) if pd.notna(m.event_group) and str(m.event_group) else str(m.market_id)
        for horizon in horizons:
            # Week 2 cutoff is the externally adjudicated information deadline, NOT necessarily
            # known in advance. Strict mode requires a contemporaneous scheduled endDate snapshot.
            T = int(m.information_cutoff_ts) - int(horizon)*DAY
            if T < 0 or (pd.notna(m.start_ts) and T < int(m.start_ts)):
                reject('before_market_start');continue
            known = snap_groups.get(m.market_id)
            historical_question = None
            deadline = None
            if known is not None:
                for snap in known.loc[known.ts.le(T)].sort_values('ts',ascending=False).itertuples():
                    d = _deadline(snap.raw_json)
                    if d is not None:
                        deadline=d
                        try: historical_question=json.loads(snap.raw_json).get('question')
                        except (ValueError,TypeError,AttributeError): historical_question=None
                        break
            if deadline_policy=='strict':
                if deadline is None:
                    reject('missing_historical_deadline_snapshot');continue
                if deadline != int(m.information_cutoff_ts):
                    reject('deadline_disagrees_with_verified_cutoff');continue
                if not historical_question:
                    reject('missing_historical_question');continue
            else:
                deadline = deadline if deadline is not None else int(m.information_cutoff_ts)
                historical_question = historical_question or m.question
            if T >= int(m.verified_resolution_ts) or T >= int(m.information_cutoff_ts):
                reject('already_final');continue
            valid=hist.loc[hist.ts.le(T)]
            if valid.empty:
                reject('no_price_before_forecast');continue
            last=valid.iloc[-1]
            p_ts=int(last.ts);p=float(last.price)
            if T-p_ts > stale_hours*3600:
                reject('stale_price');continue
            # A historical timestamp alone does not prove that a retrospective API
            # backfill was available to THIS pipeline in real time. Preserve distinction.
            fetched=provenance_map.get((str(m.token_yes),p_ts))
            if not allow_late_backfill and (fetched is None or fetched>T):
                reject('price_not_prospectively_observed');continue
            older=valid.loc[valid.ts.le(T-DAY)]
            old=older.iloc[-1] if not older.empty else None
            win=valid.loc[valid.ts.gt(T-window_days*DAY)]
            def evidence_count(g,stamp,key):
                if g is None:return 0
                # A retrospective data harvest may discover evidence that existed earlier.
                # Strict prospective policy requires BOTH event time and fetched_at <= T.
                eligible=g.loc[pd.to_numeric(g[stamp],errors='coerce').le(T) & pd.to_numeric(g[stamp],errors='coerce').gt(T-window_days*DAY)]
                if not allow_late_backfill:
                    eligible=eligible.loc[pd.to_numeric(eligible.fetched_at,errors='coerce').le(T)]
                return int(eligible[key].nunique())
            r={'market_id':str(m.market_id),'event_group':group,'question':historical_question,
               'category':m.category,'horizon_days':int(horizon),'forecast_ts':T,
               'information_cutoff_ts':int(m.information_cutoff_ts),
               'resolve_ts':int(m.verified_resolution_ts),'deadline_ts':int(deadline),
               'market_price':p,'price_timestamp':p_ts,'price_fetched_at':fetched,
               'price_age_hours':(T-p_ts)/3600,
               'price_change_24h':float(p-float(old.price)) if old is not None else np.nan,
               f'price_vol_{window_days}d':float(win.price.std(ddof=0)) if len(win)>=3 else np.nan,
               'n_price_points':len(win),
               'news_count':evidence_count(news_groups.get(m.market_id),'published_ts','url'),
               'social_count':evidence_count(social_groups.get(m.market_id),'created_ts','post_id'),
               'outcome':int(m.verified_outcome),'label_verified_source':m.verified_source,
               'label_checked_at':int(m.checked_at) if pd.notna(m.checked_at) else None,
               'point_in_time_verified':int(deadline_policy=='strict' and not allow_late_backfill)}
            for sym,a in fin_groups.items():
                # Conservative daily close release lag, shared with earlier architecture.
                valid_fin=a.loc[pd.to_numeric(a.ts,errors='coerce').add(DAY).le(T)]
                valid_fin=valid_fin.loc[pd.to_numeric(valid_fin.close,errors='coerce').gt(0)]
                prev=valid_fin.loc[valid_fin.ts.le(T-window_days*DAY-DAY)]
                r[f'ret_{window_days}d_{sym}']=float(valid_fin.iloc[-1].close/prev.iloc[-1].close-1) if len(valid_fin) and len(prev) else np.nan
            rows.append(r)
    df=pd.DataFrame(rows)
    if df.empty:
        raise ValueError('No eligible observations. Exclusions: '+json.dumps(checks['excluded'],sort_keys=True)+'. For historical backtests, explicitly select retrospective policy / late backfill and report their limitations.')
    # Final outcome may be checked retrospectively, but is NEVER an input feature.
    assert (df.price_timestamp<=df.forecast_ts).all()
    assert (df.forecast_ts<df.information_cutoff_ts).all()
    assert (df.forecast_ts<df.resolve_ts).all()
    if not allow_late_backfill:
        assert (df.price_fetched_at<=df.forecast_ts).all()
    groups=df.groupby('event_group').agg(first_forecast=('forecast_ts','min'),last_resolution=('resolve_ts','max')).reset_index()
    mapping,purged=_ordered_splits(groups,train_frac,val_frac,int(embargo_hours*3600))
    df['split']=df.event_group.map(mapping)
    excluded_purged=int(df.split.eq('purged').sum())
    df=df.loc[df.split.ne('purged')].sort_values(['forecast_ts','market_id','horizon_days']).reset_index(drop=True)
    assert df.groupby('event_group').split.nunique().max()==1
    first={s:int(df.loc[df.split.eq(s),'forecast_ts'].min()) for s in ('train','validation','test')}
    assert int(df.loc[df.split.eq('train'),'resolve_ts'].max())+embargo_hours*3600 <= first['validation']
    assert int(df.loc[df.split.eq('validation'),'resolve_ts'].max())+embargo_hours*3600 <= first['test']
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(out,index=False)
    for s in ('train','validation','test'):
        df.loc[df.split.eq(s)].to_csv(out.with_name(s+'.csv'),index=False)
    report={**checks,'included_observations':len(df),'included_markets':int(df.market_id.nunique()),
            'included_event_groups':int(df.event_group.nunique()),'purged_event_groups':purged,
            'purged_observations':excluded_purged,
            'split_observations':{k:int(v) for k,v in df.split.value_counts().items()},
            'horizon_observations':{str(k):int(v) for k,v in df.horizon_days.value_counts().items()},
            'missing_price_change_24h':int(df.price_change_24h.isna().sum()),
            'max_price_age_hours':float(df.price_age_hours.max()),
            'positive_rate':float(df.outcome.mean()),
            'warnings':['Strict mode requires on-time historical deadline snapshots, prices and retrieval. A later-fetched article or price cannot be treated as prospectively observed.',
                        'Market labels and horizon deadlines must be externally verified; strict snapshot match does not establish immutable rules.',
                        'Financial close availability assumes 24h lag; exchange calendars/corporate actions remain a limitation.',
                        'The dataset is NOT sufficient for causal historical RAG without a separately frozen evidence index.']}
    report_path=out.with_name('quality_report.json')
    report_path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return df,report


def _table_exists(conn,name):
    return conn.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',(name,)).fetchone() is not None


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db',default='polymarket_fyp.db')
    ap.add_argument('--horizons',type=int,nargs='+',default=[1,3,7])
    ap.add_argument('--out',default='research_dataset.csv')
    ap.add_argument('--stale-hours',type=float,default=24)
    ap.add_argument('--window-days',type=int,default=7)
    ap.add_argument('--train-frac',type=float,default=.6)
    ap.add_argument('--val-frac',type=float,default=.2)
    ap.add_argument('--embargo-hours',type=float,default=0)
    ap.add_argument('--deadline-policy',choices=('strict','retrospective'),default='strict')
    ap.add_argument('--allow-late-backfill',action='store_true',help='Exploratory only: permits prices/evidence fetched after prediction time')
    a=ap.parse_args()
    _,report=build(a.db,a.horizons,a.out,a.stale_hours,a.window_days,a.train_frac,a.val_frac,a.embargo_hours,a.deadline_policy,a.allow_late_backfill)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
