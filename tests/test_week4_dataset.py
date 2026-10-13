import json
import sqlite3
from datetime import datetime, timezone

import pytest

from common import get_db
from week2_spec import install as install_week2
from week3_pipeline import install as install_week3
from build_dataset import build, _ordered_splits
import pandas as pd

DAY=86400
BASE=1700000000


def fixture_db(tmp_path, count=10, late_price=False, bad_deadline=False):
    path=tmp_path/'test.db'
    c=get_db(str(path));install_week3(c)
    for i in range(count):
        cutoff=BASE+i*30*DAY
        mid=f'm{i}';token=f't{i}';group=f'event{i}'
        c.execute('INSERT INTO markets(market_id,question,token_yes,start_ts,end_ts,closed_ts,outcome) VALUES(?,?,?,?,?,?,?)',
                  (mid,f'Question {i}?',token,cutoff-40*DAY,cutoff,cutoff+DAY,i%2))
        c.execute('INSERT INTO w2_selection(market_id,event_group,provisional,verified,reason,reviewed_at) VALUES(?,?,?,?,?,?)',
                  (mid,group,1,1,'verified',cutoff+2*DAY))
        c.execute('INSERT INTO w2_resolution_checks(market_id,verified_outcome,verified_resolution_ts,information_cutoff_ts,verified_source,rules_archived,checked_at) VALUES(?,?,?,?,?,?,?)',
                  (mid,i%2,cutoff+DAY,cutoff,'independent',1,cutoff+2*DAY))
        deadline=cutoff+(DAY if bad_deadline and i==0 else 0)
        raw=json.dumps({'endDate':datetime.fromtimestamp(deadline,timezone.utc).isoformat(),'question':f'Question {i}?'})
        c.execute('INSERT INTO w3_snapshots VALUES (?,?,?)',(mid,cutoff-9*DAY,raw))
        for h in (1,3,7):
            t=cutoff-h*DAY
            for ago,price in ((DAY+3600,.4),(3600,.55)):
                ts=t-ago
                fetched=t+1 if late_price else ts+60
                c.execute('INSERT OR IGNORE INTO price_history VALUES(?,?,?)',(token,ts,price))
                c.execute('INSERT OR IGNORE INTO w3_price_provenance VALUES(?,?,?,?)',(token,ts,fetched,'test'))
        c.execute('INSERT INTO news(market_id,url,published_ts,fetched_at) VALUES(?,?,?,?)',
                  (mid,f'https://example.org/{i}',cutoff-7*DAY-3600,cutoff-7*DAY-1800))
        c.execute('INSERT INTO social_posts(market_id,post_id,created_ts,fetched_at) VALUES(?,?,?,?)',
                  (mid,f'post{i}',cutoff-7*DAY-3600,cutoff-7*DAY-1800))
    c.commit();c.close()
    return path


def test_full_strict_pipeline(tmp_path):
    db=fixture_db(tmp_path)
    df,r=build(str(db),out=str(tmp_path/'research_dataset.csv'))
    assert set(df.split)=={'train','validation','test'}
    assert set(df.horizon_days)=={1,3,7}
    assert len(df)==30
    assert df.groupby('event_group').split.nunique().max()==1
    assert (df.price_timestamp<=df.forecast_ts).all()
    assert (df.price_fetched_at<=df.forecast_ts).all()
    assert (df.forecast_ts<df.information_cutoff_ts).all()
    assert (tmp_path/'quality_report.json').exists()
    assert all((tmp_path/(s+'.csv')).exists() for s in ('train','validation','test'))
    assert r['retrospective_exploratory_only'] is False


def test_historical_deadline_mismatch_excluded(tmp_path):
    db=fixture_db(tmp_path,bad_deadline=True)
    df,r=build(str(db),out=str(tmp_path/'dataset.csv'))
    assert 'm0' not in set(df.market_id)
    assert r['excluded']['deadline_disagrees_with_verified_cutoff']==3


def test_late_prices_blocked(tmp_path):
    db=fixture_db(tmp_path,late_price=True)
    with pytest.raises(ValueError,match='No eligible observations'):
        build(str(db),out=str(tmp_path/'dataset.csv'))
    df,r=build(str(db),out=str(tmp_path/'dataset.csv'),allow_late_backfill=True)
    assert len(df)==30 and r['allow_late_backfill']
    assert (df.point_in_time_verified==0).all()


def test_split_purges_future_labels():
    groups=pd.DataFrame({'event_group':[str(x) for x in range(10)],
                         'first_forecast':[x*10 for x in range(10)],
                         'last_resolution':[x*10+2 for x in range(10)]})
    mapping,_=_ordered_splits(groups,.6,.2,0)
    assert set(mapping.values())=={'train','validation','test'}
    groups.loc[5,'last_resolution']=200
    mapping,removed=_ordered_splits(groups,.6,.2,0)
    assert mapping['5']=='purged' and '5' in removed


def test_bad_inputs(tmp_path):
    db=fixture_db(tmp_path)
    with pytest.raises(ValueError,match='Horizons'):
        build(str(db),horizons=[0])
    with pytest.raises(ValueError,match='Invalid split'):
        build(str(db),train_frac=.9,val_frac=.2)
