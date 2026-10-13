import sqlite3
from types import SimpleNamespace
import pandas as pd
import pytest
from common import SCHEMA
from week6 import evidence_from_db, model_payload, make_prompt, validate_response, score


def row():
    return SimpleNamespace(market_id='m1',question='Will Alpha win?',forecast_ts=1000)


def test_temporal_evidence_strict_and_exploratory():
    conn=sqlite3.connect(':memory:');conn.executescript(SCHEMA)
    conn.execute('INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)',('m1','https://x/a','Alpha polls','x','en','US',800,'q',900))
    conn.execute('INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)',('m1','https://x/b','Alpha wins','x','en','US',700,'q',1100))
    conn.execute('INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)',('m1','https://x/c','Alpha update','x','en','US',1200,'q',900))
    conn.execute('INSERT INTO social_posts VALUES (?,?,?,?,?,?,?,?,?,?)',('m1','p','reddit',800,'Alpha rumor','Alpha speculation',0,0,'test',1200))
    strict=evidence_from_db(conn,row());assert len(strict)==1 and strict[0]['url']=='https://x/a'
    exploratory=evidence_from_db(conn,row(),strict=False)
    assert len(exploratory)==3
    assert all(e['published_ts']<=1000 for e in exploratory)


def test_prompt_never_exposes_label_or_price():
    r=SimpleNamespace(market_id='m1',question='Alpha wins?',forecast_ts=1000,outcome=1,market_price=.97)
    payload=model_payload(r,[])
    prompt=make_prompt(payload)
    assert 'market_price' not in prompt and 'outcome' not in payload and '0.97' not in prompt
    initial={'probability':.4,'reasoning':'unknown','evidence_ids':[],'uncertainty':'high','outcome':1,'market_price':.99}
    audit=make_prompt(model_payload(r,[],initial),True)
    assert 'market_price' not in audit and '0.99' not in audit and '"outcome"' not in audit


def test_response_validation():
    valid={'probability':.4,'reasoning':'reason','evidence_ids':['news:x'],'uncertainty':'high'}
    assert validate_response(valid,['news:x'])['probability']==.4
    for bad in [{**valid,'probability':float('nan')},{**valid,'probability':'0.4'},
                {**valid,'evidence_ids':['future']},{**valid,'reasoning':''}]:
        with pytest.raises(ValueError):validate_response(bad,['news:x'])


def test_brier_uses_unclipped_probabilities():
    df=pd.DataFrame({'outcome':[1,0],'raw_probability':[1.,0.]})
    s=score(df,'raw_probability')
    assert s['brier']==0 and s['n']==2 and s['log_loss']<1e-9
