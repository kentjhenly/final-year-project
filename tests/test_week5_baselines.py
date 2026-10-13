import numpy as np
import pandas as pd
import pytest
from week5_baselines import load_dataset, evaluate, scores, bins, feature_columns


def sample():
    rows=[]
    for i in range(12):
        split='train' if i<6 else 'validation' if i<9 else 'test'
        for h in (1,3,7):
            t=1_700_000_000+i*30*86400-h*86400
            rows.append(dict(market_id=f'm{i}',event_group=f'e{i}',forecast_ts=t,
              resolve_ts=t+h*86400+86400,information_cutoff_ts=t+h*86400,
              price_timestamp=t-600,price_fetched_at=t-500,point_in_time_verified=1,
              market_price=0.2+0.6*(i%2),outcome=i%2,split=split,horizon_days=h,
              price_change_24h=0.02,price_vol_7d=0.05,news_count=i,
              label_checked_at=t+100000,leaky_numeric_target=i%2))
    return pd.DataFrame(rows)


def test_end_to_end(tmp_path):
    p=tmp_path/'data.csv';sample().to_csv(p,index=False)
    df=load_dataset(p)
    assert 'leaky_numeric_target' not in feature_columns(df)
    assert 'label_checked_at' not in feature_columns(df)
    result=evaluate(df,tmp_path/'out')
    assert len(result)==8
    assert (tmp_path/'out'/'test_predictions.csv').exists()
    assert (tmp_path/'out'/'reliability_logistic.png').exists()
    assert (tmp_path/'out'/'experiment_config.json').exists()

@pytest.mark.parametrize('column,value,match',[
 ('point_in_time_verified',0,'Unverified'),('price_fetched_at',9999999999,'fetched'),
 ('price_timestamp',9999999999,'Non-causal'),('market_price',1.2,'Market price'),
 ('outcome',2,'Outcome'),('horizon_days',0,'horizon')])
def test_invalid(tmp_path,column,value,match):
    df=sample();df.loc[0,column]=value;p=tmp_path/'bad.csv';df.to_csv(p,index=False)
    with pytest.raises(ValueError,match=match):load_dataset(p)


def test_leaked_train_label(tmp_path):
    df=sample();df.loc[df.split=='train','resolve_ts']=df.loc[df.split=='test','forecast_ts'].max()+10000
    p=tmp_path/'bad.csv';df.to_csv(p,index=False)
    with pytest.raises(ValueError,match='Outcome availability'):load_dataset(p)


def test_group_overlap(tmp_path):
    df=sample();df.loc[df.market_id=='m9','event_group']='e0'
    p=tmp_path/'bad.csv';df.to_csv(p,index=False)
    with pytest.raises(ValueError,match='Event group'):load_dataset(p)


def test_exploratory_override(tmp_path):
    df=sample();df['point_in_time_verified']=0;df['price_fetched_at']=df.forecast_ts+20
    p=tmp_path/'data.csv';df.to_csv(p,index=False)
    with pytest.raises(ValueError):load_dataset(p)
    assert len(load_dataset(p,allow_exploratory=True))==len(df)


def test_metrics_and_endpoint_bins():
    assert scores([0,1],[0,1])['brier']==0
    d=bins([0,1],[0,1]);assert d.n.sum()==2 and d.loc[9,'n']==1
    assert np.isfinite(scores([0,1],[0,1])['log_loss'])
