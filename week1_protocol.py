"""Week 1 research-protocol quality gates. Standard library only.

Usage: python week1_protocol.py --dataset research_dataset.csv --out week1_validation.json
Does not train models or claim historical evidence is leakage-free.
"""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED = ('market_id','question','horizon_days','forecast_ts','resolve_ts','market_price','outcome','split')


def validate_rows(rows):
    errors, warnings = [], []
    counts = Counter()
    groups = defaultdict(set)
    split_times = defaultdict(list)
    seen = set()
    for number, row in enumerate(rows, start=2):
        counts['rows'] += 1
        missing = [k for k in REQUIRED if not row.get(k, '').strip()]
        if missing:
            errors.append(f'row {number}: missing {missing}')
            continue
        try:
            mid = row['market_id']
            horizon = float(row['horizon_days'])
            forecast = int(float(row['forecast_ts']))
            resolved = int(float(row['resolve_ts']))
            price = float(row['market_price'])
            label = int(row['outcome'])
        except ValueError:
            errors.append(f'row {number}: invalid numeric field')
            continue
        if not (math.isfinite(price) and 0 <= price <= 1):
            errors.append(f'row {number}: invalid probability {price}')
        if label not in (0,1):
            errors.append(f'row {number}: label not binary')
        if not (horizon > 0 and forecast < resolved):
            errors.append(f'row {number}: invalid forecast horizon/order')
        if abs((resolved-forecast)-horizon*86400)>1:
            warnings.append(f'row {number}: prediction time tied to resolution timestamp, not independently scheduled event time')
        split = row['split']
        if split not in ('train','validation','test'):
            errors.append(f'row {number}: unexpected split {split}')
        groups[mid].add(split)
        split_times[split].append(resolved)
        key = (mid,horizon,forecast)
        if key in seen:
            errors.append(f'row {number}: duplicate market/horizon/timestamp')
        seen.add(key)
        counts[f'split_{split}'] += 1
    for mid,splits in groups.items():
        if len(splits)>1:
            errors.append(f'market {mid}: crosses splits {sorted(splits)}')
    if split_times['train'] and split_times['test'] and max(split_times['train']) > min(split_times['test']):
        errors.append('train/test resolution periods overlap or run backwards')
    if split_times['validation'] and split_times['test'] and max(split_times['validation']) > min(split_times['test']):
        errors.append('validation/test resolution periods overlap or run backwards')
    if counts['rows']==0:
        errors.append('dataset empty')
    if counts['split_test']==0:
        errors.append('test partition empty')
    if counts['split_train']==0:
        errors.append('train partition empty')
    warnings += [
        'Historical LLM knowledge leakage cannot be ruled out from this CSV.',
        'Publication timestamps and retrieval availability cannot be independently verified from this CSV.',
        'Market outcome labels must be independently reconciled with authoritative resolutions.',
        'Cross-market correlated events and event-level train/test isolation require separate metadata.',
        'A validation split is needed for honest model selection/calibration if absent.',
    ]
    return {'status':'FAIL' if errors else 'STRUCTURAL_PASS_ONLY',
            'counts':dict(counts),'markets':len(groups),'errors':errors,'warnings':warnings}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', required=True)
    p.add_argument('--out',default='week1_validation.json')
    args=p.parse_args()
    with open(args.dataset,newline='',encoding='utf-8-sig') as f:
        r=csv.DictReader(f)
        if not set(REQUIRED).issubset(r.fieldnames or []):
            report={'status':'FAIL','errors':['missing headers: '+str(sorted(set(REQUIRED)-set(r.fieldnames or [])))], 'warnings':[]}
        else:
            report=validate_rows(r)
    Path(args.out).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 1 if report['status']=='FAIL' else 0

if __name__=='__main__':
    raise SystemExit(main())
