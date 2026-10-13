# Week 4 exhaustive implementation audit (2026-10-13)

## Original Week 4 promises and disposition

Source of the baseline: original Week 4 response and `week4_package.zip` (`week4/build_week4.py`, `week4/README.md`). Actual project reviewed: `final-year-project-3.zip`. Status below distinguishes the **original code** from this **patched package**.

| Requirement / subpoint | Original status | Patched status / location | Qualification |
|---|---|---|---|
| Clean invalid binary outcomes | Partial | `build_dataset.build`, verified outcome filter and conflict rejection | Requires human-authenticated Week 2 entries; script cannot independently adjudicate |
| Exclude unresolved/void markets | Partial | `build`, joins `w2_resolution_checks` | Verified data prerequisite |
| Remove invalid prices | Partial | `build`, `price_groups` filter | Invalid timestamps/prices excluded |
| Duplicate handling | Partial | `build`, conflicting duplicate timestamp rejection | Primary key generally prohibits duplicates in SQLite |
| Three horizons 1,3,7 days | Partial (Week 4 CSV variant), original DB script also 14d | `build`, configurable `--horizons 1 3 7` | Anchored to externally adjudicated cutoff; see deadline caveat |
| Snapshot per market and forecast | Partial | `build`, market x horizon rows | Skip when insufficient coverage |
| Historical price at/before forecast | Partial | `build`, as-of historical prices | Strict mode also requires observed-before-forecast `w3_price_provenance` |
| Max price age / missing coverage | Partial | `build`, staleness filter / exclusion breakdown | Default 24h |
| Price change over prior day | Partial | `build`, `price_change_24h` | Missing remains NaN, no future imputation |
| Windowed market volatility | Partial | `build`, `price_vol_<window>d` | Descriptive volatility, not future price variation |
| Market metadata / immutable questions | Missing | `build`, `w3_snapshots` historical question + deadline | In strict mode recorded snapshot required |
| Known ex-ante deadline | Missing | `build._deadline`, strict deadline match | **Unresolved assumption:** external Week 2 information cutoff was genuinely ex-ante. Snapshot deadline agreement is strong but not proof of unchanged rules. |
| Outcome used only as label | Partial | `build`, separate outcome field | Consumers must explicitly drop label, resolve, information cutoff, deadline, split and audit columns from model features |
| News and social history | Partial | `build.evidence_count` as-of count and retrieval filter | NOT a substitute for temporal RAG corpus and frozen retrieval index |
| Historical volume_24h | Missing | Still missing | Current total volume is post-hoc; no verified 24h historical aggregation available. Never replace with current volume. |
| Financial macro series | Partial | `build`, 24-hour conservative lag | Historical adjustments and actual exchange release calendars remain unverified |
| Chronological train/validation/test | Missing in DB script | `build._ordered_splits` 60/20/20 group split | Deterministic, may fail intentionally with too few groups |
| No same market across partitions | Partial | Grouping by Week 2 `event_group` | Accuracy depends on correctness of group linkage |
| Correlated event grouping | Missing | Week 2 `event_group` grouping | Semantically correlated separate events might still require manual regrouping |
| Purging / embargo for future-known labels | Missing | `_ordered_splits`, configurable `--embargo-hours` | Strictly requires earlier outcomes resolved before next group's first forecast |
| Export research dataset and train/validation/test | Partial | `build`, four CSV files | Preserves prior names such as `market_price`, `forecast_ts`, `outcome`, `horizon_days` |
| Quality report and counts | Missing in DB script | `quality_report.json` | Includes exclusions, missing feature count, horizon and split counts |
| Reproducibility | Partial | Fixed defaults, event grouping, CLI + test harness | Pin dependencies and hash inputs for formal publication; currently no manifest hash |
| Week 5 market/statistical baselines | Interface only | Existing columns retained | Week 5 model scripts were not in supplied project; untested integration |
| Week 6 temporal RAG and LLM | Interface only | `forecast_ts`, `question`, `event_group` exported | Temporal evidence store, prompts, retrieval and agent outputs belong to Week 6 |
| Week 7 Jev and supervised calibration | Interface only | Held-out splits & binary labels exported | Jev, stacking, calibration and evaluation not included and not claimed |
| Automated Week 4 tests | Missing | `tests/test_week4_dataset.py` | Synthetic positive and negative tests pass |

## Bugs and methodological flaws in old implementation

1. `build_dataset.build` selected `resolve_ts = closed_ts or end_ts`, then calculated `T = resolve_ts - horizon`. `closed_ts` was only known retrospectively; horizon placement thus depended on future realized close. Use a verified cutoff and prove its scheduled nature via a historical on-time snapshot in strict mode.
2. `build_dataset.build` queried `WHERE outcome IS NOT NULL`, ignoring `w2_resolution_checks`, external verification and archived rules. The corrected join requires verified selection and independently checked outcome.
3. `build_dataset.build` queried news/social counts by `published_ts`/`created_ts` alone. Backfilled evidence and mutable social counts could masquerade as available at forecast time. Corrected counts use `fetched_at` as well unless explicitly exploratory. Count-only representation avoids using later scores/comments.
4. `build_dataset.build` used historical price `ts` alone, not `w3_price_provenance.fetched_at`. The corrected strict check requires a point to have been prospectively fetched.
5. `build_dataset.build` used a resolution-time quantile 70/30 split and could separate related markets, put early forecasts from later markets before early-train market resolutions, and had no validation set. Corrected grouped chronological split with explicit label-availability purge.
6. The earlier separate `week4/build_week4.py` expected `markets.csv` / `prices.csv`, included its own naming scheme, and was never wired to the project SQLite schema. It also only warned about event grouping and historical deadline provenance. That script is not copied into the updated project.
7. The original 24h change used an earlier price with no freshness bound; retained as an optional missing-valued signal when historical 24h comparison is absent, not imputed with future data.
8. Historical external financial close availability is modeled with a blanket +24h assumption. This remains a methodological limitation until symbol-specific release timestamps and point-in-time adjustment policies are recorded.
9. Strict mode can legitimately produce **zero** data if historical prices were first retrieved after each prediction timestamp. Using `--allow-late-backfill` is possible **only for exploratory retrospective analysis** and must not be described as prospective observation.
10. Week 2 `information_cutoff_ts` is manually verified after resolution and can itself encode knowledge discovered after the fact. Historical `endDate` agreement does not prove past visibility of externally determined rules or the true information cutoff. Independently archive event rules and prove the deadline's historical validity before stating fully leakage-safe empirical conclusions.

## Files changed

- `build_dataset.py`: replaced its Week 4 processing and CLI only; no other week modules changed.
- `tests/test_week4_dataset.py`: new isolated synthetic test fixtures and 5 tests.
- `WEEK4_AUDIT.md`: this audit.
- `WEEK4_README.md`: execution and dataset contract.

## Commands / verification

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python build_dataset.py --db polymarket_fyp.db --out research_dataset.csv
```

For a **clearly labeled retrospective exploratory** run, when data collection was after historical forecast times:

```bash
python build_dataset.py --db polymarket_fyp.db --out exploratory_dataset.csv --deadline-policy retrospective --allow-late-backfill
```

**Do not** treat exploratory results as leakage-safe FYP backtest evidence.

## Tested and untested

Locally verified: tests pass on synthetic SQLite data; invalid deadlines and post-forecast retrieval are rejected, event-level splits and label purging behave as asserted. No real DB was included in archive; no real research rows, resolution source authenticity or Weeks 5–7 integration were empirically verified. A 24-hour availability lag for financial closes and snapshot rule authenticity remain assumptions, not established properties.
