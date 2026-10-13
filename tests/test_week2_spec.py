import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import get_db
from week2_spec import audit_markets,verify_resolution,selection

class Week2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=get_db(str(Path(self.tmp.name)/'test.sqlite'))
        self.db.execute('''INSERT INTO markets(market_id,condition_id,event_slug,question,resolution_source,token_yes,token_no,start_ts,end_ts,closed_ts,outcome,raw_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',('m1','c1','event-A','Will event occur?','https://example.org/verifier','yes-token','no-token',100000,2000000,1950000,1,json.dumps({'outcomes':['Yes','No'],'clobTokenIds':['yes-token','no-token']})))
        self.db.execute('INSERT INTO price_history VALUES(?,?,?)',('yes-token',1900000-86400,0.4))
        self.db.execute('INSERT INTO price_history VALUES(?,?,?)',('yes-token',1900000-86400+50,0.9))
        self.db.commit()
    def tearDown(self): self.db.close();self.tmp.cleanup()
    def test_unverified_by_default(self):
        audit_markets(self.db,(1,))
        self.assertEqual(self.db.execute('SELECT verified FROM w2_selection').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT status FROM w2_price_coverage').fetchone()[0],'requires_verified_resolution_and_historical_rules')
    def test_no_future_prices(self):
        verify_resolution(self.db,'m1',1,1950000,1900000,'https://example.org/verifier',True)
        audit_markets(self.db,(1,),24)
        row=self.db.execute('SELECT selected_price,status FROM w2_price_coverage').fetchone()
        self.assertEqual(row[0],0.4)
        self.assertEqual(row[1],'eligible')
    def test_reject_missing_verification(self):
        with self.assertRaises(ValueError): verify_resolution(self.db,'m1',1,1950000,1900000,'',False)
    def test_stale_history(self):
        verify_resolution(self.db,'m1',1,1950000,1900000,'https://example.org/verifier',True)
        self.db.execute('DELETE FROM price_history')
        self.db.execute('INSERT INTO price_history VALUES(?,?,?)',('yes-token',1800000,0.4))
        audit_markets(self.db,(1,),1)
        self.assertEqual(self.db.execute('SELECT status FROM w2_price_coverage').fetchone()[0],'stale_history')
    def test_invalid_binary(self):
        m=dict(self.db.execute('SELECT * FROM markets').fetchone()) if self.db.row_factory else None
        self.db.row_factory=sqlite3.Row
        m=dict(self.db.execute('SELECT * FROM markets').fetchone())
        m['raw_json']=json.dumps({'outcomes':['A','B'],'clobTokenIds':['a','b']})
        self.assertFalse(selection(m)[0])
if __name__=='__main__': unittest.main()
