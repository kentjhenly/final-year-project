import json
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from common import SCHEMA
from week7 import prepare, validate, infer, run


def row():
    return SimpleNamespace(market_id='m1', event_group='g1', question='Will Alpha win?',
                           forecast_ts=1000, horizon_days=7, split='validation',
                           outcome=1, market_price=0.99)


def evidence(fetched=900):
    return {'id':'news:1', 'title':'Alpha poll', 'text':'Alpha leads', 'source':'example',
            'published_ts':800, 'fetched_at':fetched, 'available_ts':max(800,fetched)}


def test_prompt_allowlist():
    messages, digest, ids = prepare(row(), [evidence()])
    prompt = json.dumps(messages)
    assert ids == ['news:1'] and len(digest) == 64
    assert 'market_price' not in messages[1]['content'] and 'outcome' not in messages[1]['content'] and '0.99' not in prompt
    assert 'Alpha poll' in prompt


def test_late_fetched_rejected():
    with pytest.raises(ValueError, match='after forecast'):
        prepare(row(), [evidence(1001)])


@pytest.mark.parametrize('bad', [{'probability':True}, {'probability':'0.4'}, {'probability':float('nan')},
    {'probability':1.1}, {'probability':.5, 'evidence_ids':['future']},
    {'probability':.5, 'evidence_ids':['news:1','news:1']}])
def test_validate_rejects_invalid(bad):
    payload={'probability':0.5, 'reasoning':'Reason', 'uncertainty':'High', 'evidence_ids':['news:1']}
    payload.update(bad)
    with pytest.raises(ValueError):validate(payload,['news:1'])


def test_infer_retry_error_and_success():
    count=[0]
    def call(_):
        count[0]+=1
        if count[0]==1:raise RuntimeError('transient')
        return {'probability':.4,'reasoning':'Reason', 'uncertainty':'High','evidence_ids':[]}
    assert infer([],[], 'mock', caller=call, retries=1, sleeper=lambda _:None)['status']=='ok'
    assert count[0] == 2
    assert infer([],[], 'mock', caller=lambda _: {'probability':False}, retries=0)['status']=='error'


def test_run_project_integration(tmp_path, monkeypatch):
    db=tmp_path/'test.db'
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.execute('INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)',('m1','https://x/a','Alpha polls','x','en','US',800,'q',900))
        conn.execute('INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)',('m1','https://x/b','Alpha wins','x','en','US',800,'q',1100))
    df=pd.DataFrame([{'market_id':'m1','event_group':'g1','forecast_ts':1000,'horizon_days':7,
                      'split':'validation','question':'Will Alpha win?', 'outcome':1,'market_price':.99}])
    monkeypatch.setattr('week7.load_dataset',lambda *a, **k: df)
    args=SimpleNamespace(input='dummy',db=str(db), output=str(tmp_path/'out'), mode='forecast',
        split='validation',model='mock',base_url=None,key_env='FOO',top_k=8,retries=0,
        max_rows=None,allow_exploratory=False,allow_test=False)
    def caller(messages):
        assert 'https://x/b' not in json.dumps(messages)
        assert 'Alpha wins' not in json.dumps(messages)
        return {'probability':.4,'reasoning':'Limited evidence','uncertainty':'high','evidence_ids':[]}
    result=run(args, caller)
    assert result['completed']==1 and result['paired_scores']['raw_probability']['brier']==pytest.approx(.36)
    records=[json.loads(x) for x in (tmp_path/'out/week7_forecasts.jsonl').read_text().splitlines()]
    assert records[0]['status']=='ok' and records[0]['evidence_count']==1
    args.split='test'
    with pytest.raises(ValueError,match='allow-test'):run(args,caller)
