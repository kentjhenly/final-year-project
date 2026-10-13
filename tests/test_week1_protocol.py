import unittest
from week1_protocol import validate_rows

BASE={'market_id':'m1','question':'Will X happen?','horizon_days':'7',
      'forecast_ts':'100000','resolve_ts':str(100000+7*86400),
      'market_price':'0.4','outcome':'1','split':'train'}

class ProtocolTests(unittest.TestCase):
    def test_structural_pass(self):
        b=dict(BASE,market_id='m2',split='test')
        self.assertEqual(validate_rows([BASE,b])['status'],'STRUCTURAL_PASS_ONLY')
    def test_future_forecast_rejected(self):
        b=dict(BASE,market_id='m2',split='test',forecast_ts='9999999')
        self.assertEqual(validate_rows([BASE,b])['status'],'FAIL')
    def test_out_of_range_probability(self):
        b=dict(BASE,market_id='m2',split='test',market_price='1.2')
        self.assertEqual(validate_rows([BASE,b])['status'],'FAIL')
    def test_cross_split_market(self):
        b=dict(BASE,split='test',horizon_days='1',forecast_ts=str(100000+6*86400))
        self.assertEqual(validate_rows([BASE,b])['status'],'FAIL')
    def test_duplicate(self):
        b=dict(BASE,market_id='m2',split='test')
        self.assertEqual(validate_rows([BASE,BASE,b])['status'],'FAIL')
    def test_missing(self):
        b=dict(BASE,market_id='m2',split='test',question='')
        self.assertEqual(validate_rows([BASE,b])['status'],'FAIL')
    def test_empty(self):
        self.assertEqual(validate_rows([])['status'],'FAIL')

if __name__=='__main__':unittest.main()
