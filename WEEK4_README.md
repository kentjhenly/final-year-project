# Week 4 research dataset builder

`build_dataset.py` is the single canonical Week 4 builder for this project. It uses the current SQLite tables, not `markets.csv`/`prices.csv` from an older standalone prototype.

## Preconditions

- Python 3.11+, dependencies in `requirements.txt`, `pytest` for testing.
- Week 2 audit completed and each market marked independently verified in `w2_selection` / `w2_resolution_checks`.
- Week 3 historical prices, `w3_price_provenance` and **on-time** `w3_snapshots` captured. Snapshots must contain `endDate` and `question` in JSON. In strict mode, the snapshot deadline must equal the independently verified `information_cutoff_ts`.
- At least 3 event groups sufficiently separated in calendar time to fill the purged temporal splits. In practice, 10+ is strongly advised.

## Run

```
python build_dataset.py --db polymarket_fyp.db --out research_dataset.csv --horizons 1 3 7 --stale-hours 24 --train-frac .6 --val-frac .2
```

Generated alongside the chosen `--out`: `train.csv`, `validation.csv`, `test.csv`, `quality_report.json`.

Strict mode is conservative: markets without timely historical observations are excluded, and the run exits with an explanation if nothing qualifies. To study historical archival data collected later, run with **both** `--deadline-policy retrospective --allow-late-backfill` and clearly label results exploratory. A retrospective label must not imply that the evidence was available to the pipeline when forecasts were supposedly made.

## Columns and downstream model contract

Identifiers: `market_id`, `event_group`, `question`, `category`, `horizon_days`, `forecast_ts`.

Market features: `market_price`, `price_change_24h`, `price_vol_7d`, `n_price_points`, `price_age_hours`, optionally conservative macro returns `ret_7d_*`.

Evidence availability counts: `news_count`, `social_count`. Actual text stays in the source tables, filtered by publish/create **and** retrieval times for strict temporal RAG.

Label: `outcome` is **ONLY** the supervised/evaluation target; `label_verified_source` and `label_checked_at` document provenance.

Audit-only columns, **never feed as features**: `resolve_ts`, `information_cutoff_ts`, `deadline_ts`, `price_timestamp`, `price_fetched_at`, `label_verified_source`, `label_checked_at`, `point_in_time_verified`, `split`. `forecast_ts`, `market_id`, `event_group` and `question` should be excluded from generic numeric baselines unless explicitly modeled. The market-blind independent LLM must **never see `market_price` or derived market-price features**; calibration can use market probabilities only in the later aggregation stage. The Jev verifier must be insulated from future labels and evidence.

`split` is chronological **by earliest forecast time for each event group**, with earlier split groups purged if any of their verified outcomes became available after the next split's first prediction timestamp. The code will fail rather than silently produce empty partitions.

## Tests

```
python -m pip install pytest
python -m pytest -q tests/test_week4_dataset.py
python -m pytest -q
```

All tests use temporary synthetic SQLite databases and require no network or credentials.

## Known limitations and research dependencies

1. Contemporaneous market snapshot matching the externally reviewed deadline is necessary but not sufficient to establish that event rules were immutable or that the external adjudicated information cutoff was truly known ex ante.
2. Backfilled historical prices/news can be used in exploratory research but cannot claim to have been prospectively observed; the flags/report distinguish this.
3. Historical 24-hour market volume cannot be calculated safely from the current total-volume field; it is intentionally omitted.
4. Adjusted financial bars and per-asset release timing require separate provenance validation. Do not use the macro return features for strict claims without verifying the source.
5. Full temporal RAG indexing, independent LLM, Jev verification and supervised calibrator are later-week modules; this builder only supplies their proper dataset contract.
6. Some semantically related event markets may evade `event_group` and must be reviewed manually; no semantic clustering is claimed.
7. No real Polymarket database was provided for this audit, so no empirical coverage, score or calibration statistic is reported.
