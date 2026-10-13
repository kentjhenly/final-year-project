"""Week 5: leakage-guarded Polymarket and logistic-regression baselines."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

CORE = ('market_id','event_group','forecast_ts','resolve_ts','market_price','outcome','split','horizon_days',
        'information_cutoff_ts','price_timestamp','price_fetched_at','point_in_time_verified')
FEATURES = ('market_price','price_change_24h','price_vol_7d','n_price_points','price_age_hours','news_count','social_count')
SPLITS = ('train','validation','test')


def load_dataset(path, allow_exploratory=False):
    path = Path(path)
    df = pd.read_parquet(path) if path.suffix.lower()=='.parquet' else pd.read_csv(path)
    missing = sorted(set(CORE)-set(df))
    if missing: raise ValueError(f'Missing Week 4 columns: {missing}')
    if df.empty: raise ValueError('Empty research dataset')
    for c in ('forecast_ts','resolve_ts','information_cutoff_ts','price_timestamp','price_fetched_at','horizon_days','outcome','market_price','point_in_time_verified'):
        df[c] = pd.to_numeric(df[c],errors='raise')
        if not np.isfinite(df[c].to_numpy(dtype=float)).all(): raise ValueError(f'Non-finite {c}')
    if df[list(CORE)].isna().any().any(): raise ValueError('Null required fields')
    if not df.outcome.isin([0,1]).all(): raise ValueError('Outcome must be 0/1')
    if not df.market_price.between(0,1).all(): raise ValueError('Market price must be in [0,1]')
    if not df.split.isin(SPLITS).all(): raise ValueError('Invalid split')
    if not (df.horizon_days>0).all(): raise ValueError('Invalid horizon')
    if df.duplicated(['market_id','forecast_ts','horizon_days']).any(): raise ValueError('Duplicate forecast rows')
    if df.groupby('market_id').outcome.nunique().gt(1).any(): raise ValueError('Conflicting outcome')
    if df.groupby('event_group').split.nunique().gt(1).any(): raise ValueError('Event group overlaps splits')
    if not ((df.price_timestamp<=df.forecast_ts)&(df.forecast_ts<df.information_cutoff_ts)&(df.forecast_ts<df.resolve_ts)).all():
        raise ValueError('Non-causal forecast or market price timestamp')
    if not allow_exploratory:
        if not df.point_in_time_verified.eq(1).all(): raise ValueError('Unverified/backfilled observations require --allow-exploratory')
        if not (df.price_fetched_at<=df.forecast_ts).all(): raise ValueError('Market price fetched after forecast')
    starts={s:df.loc[df.split.eq(s),'forecast_ts'].min() for s in SPLITS}
    if any(pd.isna(x) for x in starts.values()): raise ValueError('Train, validation and test are all required')
    if not (df.loc[df.split.eq('train'),'resolve_ts'].max() <= starts['validation'] and
            df.loc[df.split.eq('validation'),'resolve_ts'].max() <= starts['test']):
        raise ValueError('Outcome availability overlaps later split')
    if not (df.loc[df.split.eq('train'),'forecast_ts'].max() < starts['validation'] and
            df.loc[df.split.eq('validation'),'forecast_ts'].max() < starts['test']):
        raise ValueError('Chronological split ordering violated')
    return df


def feature_columns(df):
    # Deliberate allowlist. Never auto-add numeric columns: outcome, future timestamps,
    # resolution provenance and validation metadata are NOT predictors.
    return [c for c in FEATURES if c in df.columns]


def scores(y, p):
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float)
    if len(y)==0: raise ValueError('Empty evaluation set')
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any(): raise ValueError('Invalid forecast probability')
    safe=np.clip(p,1e-12,1-1e-12)
    return {'n_rows':len(y),'brier':float(brier_score_loss(y,p)),
            'log_loss':float(log_loss(y,safe,labels=[0,1])),
            'auc':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None}


def bins(y,p,n_bins=10):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    index=np.minimum(np.floor(p*n_bins).astype(int),n_bins-1)
    return pd.DataFrame([{'bin':i,'lower':i/n_bins,'upper':(i+1)/n_bins,
                          'n':int((index==i).sum()),
                          'mean_probability':float(p[index==i].mean()) if (index==i).any() else np.nan,
                          'event_rate':float(y[index==i].mean()) if (index==i).any() else np.nan}
                         for i in range(n_bins)])


def plot_reliability(frame, path, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(6,5))
    ax.plot([0,1],[0,1],'--',label='Perfect calibration')
    v=frame[frame.n.gt(0)]
    ax.plot(v.mean_probability,v.event_rate,'o-',label='Observed')
    ax.set(xlim=(0,1),ylim=(0,1),xlabel='Mean predicted probability',ylabel='Event frequency',title=title)
    ax.legend();fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)


def evaluate(df, out, allow_exploratory=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cols=feature_columns(df)
    train=df.loc[df.split.eq('train')].copy()
    test=df.loc[df.split.eq('test')].copy()
    if train.outcome.nunique()!=2: raise ValueError('Training labels require two classes')
    # Fail closed on absent feature columns; do not silently fit a different model.
    Xtrain=train[cols].apply(pd.to_numeric,errors='raise').replace([np.inf,-np.inf],np.nan)
    Xtest=test[cols].apply(pd.to_numeric,errors='raise').replace([np.inf,-np.inf],np.nan)
    usable=[c for c in cols if Xtrain[c].notna().any()]
    if 'market_price' not in usable: raise ValueError('Market price missing from predictors')
    model=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=False)),
                    ('scaler',StandardScaler()),('classifier',LogisticRegression(max_iter=2000,random_state=42))])
    model.fit(Xtrain[usable],train.outcome.astype(int))
    prediction=test[['market_id','event_group','forecast_ts','horizon_days','outcome','market_price']].copy()
    prediction['logistic_probability']=model.predict_proba(Xtest[usable])[:,1]
    prediction.to_csv(out/'test_predictions.csv',index=False)
    results=[]
    for name,column in [('market','market_price'),('logistic','logistic_probability')]:
        for horizon,chunk in [('all',prediction)]+[(str(h),part) for h,part in prediction.groupby('horizon_days',sort=True)]:
            results.append({'model':name,'horizon_days':horizon,'n_markets':chunk.market_id.nunique(),
                            'n_event_groups':chunk.event_group.nunique(),**scores(chunk.outcome,chunk[column])})
        b=bins(prediction.outcome,prediction[column]);b.to_csv(out/f'calibration_bins_{name}.csv',index=False)
        plot_reliability(b,out/f'reliability_{name}.png',name.title()+' baseline')
    metrics=pd.DataFrame(results)
    metrics.to_csv(out/'metrics.csv',index=False)
    config={'feature_allowlist_used':usable,'candidate_features':cols,'train_rows':len(train),
            'validation_rows':int(df.split.eq('validation').sum()),'test_rows':len(test),
            'test_groups':test.event_group.nunique(),'seed':42,'model':'median-imputed standardized logistic regression',
            'exploratory':bool(allow_exploratory),'tuning':'none; validation held out',
            'evaluation_warning':'Rows from the same market are correlated; no confidence intervals computed'}
    (out/'experiment_config.json').write_text(json.dumps(config,indent=2,default=int))
    return metrics


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',default='results/week5')
    parser.add_argument('--allow-exploratory',action='store_true')
    args=parser.parse_args(argv)
    df=load_dataset(args.input,args.allow_exploratory)
    result=evaluate(df,args.output,args.allow_exploratory)
    print(result.to_string(index=False))

if __name__=='__main__': main()
