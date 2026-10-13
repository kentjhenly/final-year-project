import json
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

from common import get_db
from collect_polymarket import parse_market, UPSERT, collect_markets, collect_prices, collect_trades, snapshot_open
from week3_pipeline import coverage, install, validate_history


def sample(**updates):
    x=dict(id='11',conditionId='0xabc',closed=True,slug='a',question='Will it happen?',
           outcomes='["Yes","No"]',clobTokenIds='["token1","token2"]',
           outcomePrices='["0.999","0.001"]',startDate='2024-01-01T00:00:00Z',
           endDate='2024-01-07T00:00:00Z',closedTime='2024-01-07T00:00:00Z')
    x.update(updates)
    return x

class Response:
    status_code=200
    def __init__(self,obj):self.obj=obj
    def raise_for_status(self):pass
    def json(self):return self.obj

class Week3(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conn=get_db(str(Path(self.tmp.name)/'a.db'))
        install(self.conn)
    def tearDown(self):self.conn.close();self.tmp.cleanup()
    def test_no_terminal_price_label(self):
        self.assertIsNone(parse_market(sample())['outcome'])
        self.assertIsNone(parse_market(sample(outcomePrices='["0.001","0.999"]'))['outcome'])
    def test_preserves_existing_label(self):
        row=parse_market(sample());self.conn.execute(UPSERT,row)
        self.conn.execute("UPDATE markets SET outcome=1 WHERE market_id='11'")
        self.conn.execute(UPSERT,parse_market(sample(question='Updated')))
        self.assertEqual((1,'Updated'),self.conn.execute('SELECT outcome,question FROM markets').fetchone())
    def test_price_bounds_and_range(self):
        self.assertEqual([('t',20,.4)],validate_history({'history':[{'t':20,'p':.4}]},'t',10,30))
        for h in ({'history':[{'t':40,'p':.5}]},{'history':[{'t':20,'p':1.1}]},{'oops':[]}):
            with self.assertRaises(ValueError):validate_history(h,'t',10,30)
    def test_market_request_audit_and_limit(self):
        sess=Mock();sess.get.side_effect=[Response([sample(id='11'),sample(id='12')])]
        collect_markets(self.conn,sess,85,0,1)
        self.assertEqual(1,coverage(self.conn)['markets'])
        self.assertEqual(1,coverage(self.conn)['requests'])
    def test_price_resume_and_future_cutoff(self):
        self.conn.execute(UPSERT,parse_market(sample()))
        sess=Mock();sess.get.return_value=Response({'history':[{'t':1704499200,'p':.4}]})
        collect_prices(self.conn,sess,60,14,2)
        self.assertEqual(1,self.conn.execute('SELECT COUNT(*) FROM price_history').fetchone()[0])
        collect_prices(self.conn,sess,60,14,2)
        self.assertEqual(1,sess.get.call_count)
    def test_trade_pagination(self):
        self.conn.execute(UPSERT,parse_market(sample()))
        sess=Mock();sess.get.return_value=Response([])
        collect_trades(self.conn,sess,500)
        collect_trades(self.conn,sess,500)
        self.assertEqual(1,sess.get.call_count)
    def test_snapshot_no_label(self):
        sess=Mock();sess.get.return_value=Response([sample(closed=False)])
        snapshot_open(self.conn,sess,0,1)
        self.assertEqual(1,self.conn.execute('SELECT COUNT(*) FROM w3_snapshots').fetchone()[0])
        self.assertIsNone(self.conn.execute('SELECT outcome FROM markets').fetchone()[0])

if __name__=='__main__':unittest.main()
