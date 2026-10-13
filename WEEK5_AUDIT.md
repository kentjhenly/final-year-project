# Week 5 audit and acceptance record

## Scope and original plan comparison

| Plan item | Original Week 5 package | Updated implementation | Evidence |
|---|---|---|---|
| B1 Market-only probability | Implemented for incompatible `market_probability` column | Complete for Week 4 `market_price` | `week5_baselines.evaluate`, `test_end_to_end` |
| B2 Logistic regression | Implemented with `feat_` and incompatible schema | Complete with explicit vetted Week 4 feature allowlist, median training-only imputation and scaling | `feature_columns`, `evaluate`, tests |
| B3 Brier, log-loss and ROC AUC | Implemented; clipped Brier probabilities unnecessarily | Complete; exact Brier and protected logarithm, undefined single-class AUC is null | `scores`, `test_metrics_and_endpoint_bins` |
| B4 Calibration bins and reliability charts | Implemented | Complete aggregate 10-bin plots and CSV; not yet per-horizon charts | `bins`, `plot_reliability` |
| B5 Same held-out observations / horizons | Partially implemented | Complete for baseline comparisons on one fixed held-out test dataset with separate rows by horizon | `evaluate`, `test_end_to_end` |
| B6 Reproducible experiment | CLI existed but impossible to run against canonical Week 4 | Complete executable code, pinned *minimum* dependencies, feature/config log and automated unit tests | `week5_baselines.py`, `requirements.txt`, tests |
| B7 Midterm methodology and empirical findings | Draft only | Methodology documented; real findings **not available** without real dataset | this audit; no scores asserted |

## Input contract and causal controls

The canonical Week 4 builder is `build_dataset.py`; its CSV or Parquet export is the only Week 5 input. Feature selection is an explicit allowlist: `market_price`, `price_change_24h`, `price_vol_7d`, `n_price_points`, `price_age_hours`, `news_count`, `social_count`. No text content or future outcomes are presented to the market-blind LLM later. `ret_7d_*` financial features are intentionally excluded pending provenance validation. `price_change_24h`/`price_vol_7d` are market-derived and **must not** be reused by the independent LLM.

Strict mode requires `point_in_time_verified==1`, `price_fetched_at<=forecast_ts`, `price_timestamp<=forecast_ts`, `forecast_ts<information_cutoff_ts` and `<resolve_ts`. It also requires chronological event-group-disjoint splits and training resolution before validation forecast start, and validation resolution before test forecast start. Backfilled data may only be explicitly run with `--allow-exploratory` and cannot support prospective claims.

### Leakage and interpretation caveats

- Label resolution is used as an availability proxy. Independent verification timestamps, event-group completeness and revised rule cutoffs must still be checked upstream (Week 2/4). The model never consumes these audit-only metadata fields.
- Related events not grouped under the same `event_group` can still induce correlated train/test content: manual semantic review remains necessary.
- Multiple horizons for one market are correlated. Rows are not independent; use event-group-block bootstrap uncertainty estimates before asserting significant improvement.
- The model is deliberately **not tuned**. Validation data are reserved for future hyperparameter selection and cannot be silently pooled into training. No test-set-based tuning is permitted.
- Histogram reliability curves are descriptive and sensitive to low bin counts. Per-horizon reliability is an optional extension, not silently claimed.
- `market_price` may differ from executable prices and is subject to spread, slippage and liquidity effects. Metrics measure binary forecasting, not trading profit.
- `point_in_time_verified` confirms the Week 4 *builder's declared policy*, not independent audit of whether every underlying article or market was available in real time. News/social counts are from point-in-time-safe Week 4 aggregations in strict mode.
- Historical external macro data were intentionally excluded from training pending release-time audit.

## Commands

From the repository root:

```bash
python -m pip install -r requirements.txt
python build_dataset.py --db polymarket_fyp.db --out research_dataset.csv --horizons 1 3 7
python week5_baselines.py --input research_dataset.csv --output results/week5
python -m pytest -q tests/test_week5_baselines.py
python -m pytest -q
```

For retrospective exploratory backfill only:

```bash
python week5_baselines.py --input research_dataset.csv --output results/week5_exploratory --allow-exploratory
```

Outputs: `metrics.csv`, `test_predictions.csv`, `calibration_bins_market.csv`, `calibration_bins_logistic.csv`, `reliability_market.png`, `reliability_logistic.png`, `experiment_config.json`.

## Week 1–7 interface

- Weeks 1–2: honors frozen questions, market resolution provenance and selected markets by relying on the Week 4 contract.
- Week 3: relies on Week 4's time-safe construction, with additional mandatory strict checks against fetched timestamps.
- Week 4: direct consumption of canonical export, no changes to Week 4 pipeline.
- Week 5: baseline probabilities are in `test_predictions.csv` with stable `market_id`, `event_group`, `forecast_ts`, `horizon_days`, `outcome` columns.
- Week 6: temporal RAG and independent LLM forecasting must not consume `market_price`, `price_change_24h`, volatility or market baseline outputs. Jev verification also must not consume resolution labels or post-forecast retrievals.
- Week 7: supervised calibration can consume logged market probabilities and independently produced LLM/Jev forecasts only when predictions are generated out of sample or via leakage-safe cross-fitting. Week 5 test labels cannot train that calibration model. Comparable final scoring must use the same frozen held-out splits, group boundaries and horizons.

## Verified execution and remaining work

Local run of `python -m pytest -q tests/test_week5_baselines.py`: **11 passed**. Local run of `python -m pytest -q`: **35 passed**. Tests used synthetic datasets and did not require network access. No user historical Polymarket database / real Week 4 export was available in this archive. Consequently there are **no empirical baseline scores, real-market calibration curves or statistical significance claims**. Package dependencies have unbounded upper versions and environment lockfiles are not included; bitwise reproduction across distant environments is not guaranteed.

## Acceptance checklist

- [x] Market baseline B1 implemented and tested on synthetic canonical schema
- [x] Logistic regression B2 implemented and tested on synthetic canonical schema
- [x] Brier, log-loss and optional AUC B3 implemented and tested
- [x] Reliability chart and bin CSV B4 produced in synthetic integration test
- [x] Held-out test and horizon-specific comparison B5 implemented
- [x] CLI and experiment metadata B6 implemented
- [x] Academic methodology documented B7
- [ ] Empirical B7 findings on real resolved Polymarket data (dataset not provided)
- [ ] Group-block bootstrap confidence intervals for inferential claims (not implemented)
- [ ] Independent manual semantic event grouping audit (requires market questions)
- [ ] Provenance review of macro features (deliberately excluded)
- [ ] End-to-end real SQLite ingestion and subsequent Week 6/7 agents (not available in upload)
