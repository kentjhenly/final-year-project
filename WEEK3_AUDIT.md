# Week 3 implementation audit — 2026-10-13

## Audited sources and scope

Audited uploaded `final-year-project-2.zip`, containing `week2/{common.py,collect_polymarket.py,collect_news.py,collect_external.py,build_dataset.py,week2_spec.py,week1_protocol.py,tests}`. The original standalone Week 3 starter ZIP was also inspected separately. It was **not** present inside the uploaded project. The Week 3 functionality in the uploaded project resided chiefly in `collect_polymarket.py`, with partial supporting infrastructure in `common.py` and `week2_spec.py`.

**Status vocabulary:** Verified = exercised with isolated fixtures and offline tests; Implemented, not live-verified = code exists but not exercised against public service; Partial = required aspect not established; Deferred = cross-week concern, explicitly excluded from Week 3 patch.

## Original Week 3 plan to code mapping

| Original requirement/subpoint | Original uploaded state | Patched location | Current status |
|---|---|---|---|
| D3.1 Python Gamma API client | `collect_markets`, `snapshot_open`, `get_json` | `collect_polymarket.collect_markets`, `snapshot_open`, `week3_pipeline.request` | Offline verified; **live unverified** |
| D3.1 CLOB client | `collect_prices`, no request log | `collect_prices` + `request`, `validate_history` | Offline verified; live unverified |
| D3.1 Data API client | `collect_trades`, offset paging; depth issues | `collect_trades`, w3_trade_pages | Partial: legacy `/trades` shape not proven against live API and may truncate |
| D3.1 pagination/retries | Gamma offset, requests Retry in `common.make_session` | Unchanged retry plus explicit response checks and per-window resume | Offline verified; live throttling unverified |
| D3.2 historic market selection | Closed markets filtered from Gamma by dates, volume | `collect_markets`, `parse_market` | Implemented, closed is **not verified resolution** |
| D3.2 binary/token linkage | `parse_market` checks Yes/No tokens | Kept; rejects absent market/condition ID | Offline verified |
| D3.2 objective resolution evidence | Price >=.99 became `outcome` | Removed price label; independent `week2_spec.verify_resolution` | Collection safe; independent verification manual, **not completed** |
| D3.2 market sampling | volume-ranked, last N days | Same configurable strategy | Partial: selection bias, not exhaustive population |
| D3.3 historical price timeseries | YES history, skip whole token if any history | Time-window checkpoints, point validation and provenance | Offline verified; historical gaps possible |
| D3.3 NO token prices | `token_no` recorded, NO price approximated | YES history retained, no false NO equivalence | Partial: NO historical collection not added |
| D3.3 trading activity | Trade collector | Page audit + resume + error logs | Partial: depth limits, endpoint schema, timestamps not live checked |
| D3.3 liquidity history | Historical liquidity unavailable, current value stored | Prospective snapshots include timestamped liquidity | Partial: current metadata cannot retroactively reproduce liquidity |
| D3.4 local SQLite raw database | `common.SCHEMA`, existing tables | Existing schema preserved; new `w3_*` audit tables | Verified schema creation |
| D3.4 raw metadata retention | `markets.raw_json` overwritten on refresh | Request payloads and `w3_snapshots.raw_json` retained | Verified for tests; storage can grow |
| D3.4 time/ID normalization | `iso_to_ts` and parsed JSON token IDs | Existing helpers reused | Partial: endpoint timestamp quirks need live validation |
| D3.5 validation price bounds | Not validated | `validate_history` 0..1, finite, window constraint | Verified |
| D3.5 duplicates | `INSERT OR IGNORE` | Existing keys retained + window checkpoints | Verified on price resume fixture |
| D3.5 API failures and recovery | Warnings only, no structured audit | `w3_requests`, `w3_errors`, failure windows | Verified basic success, errors not integration-tested |
| D3.5 look-ahead discipline | Historical final metadata and inferred label leak | Price labels forbidden, fetched timestamp and provenance maintained | **Partial**: historical media publication times are not automatically guaranteed availability; Week 4 must enforce cutoff |
| D3.6 dataset totals | Missing report | `week3_pipeline.coverage` JSON | Offline verified |
| D3.6 temporal coverage | No audit | first/last price timestamp in coverage | Partial: does not prove no gaps; check per-market `w2_price_coverage` after verification |
| D3.6 missingness and sampling | Not quantified | collection errors and window counts | Partial: cannot prove complete historical API coverage |
| D3.7 installation/CLI | `requirements.txt`, command examples | `WEEK3_README.md` | Verified commands syntactically / tests; live run unverified |
| D3.7 reproducible collection | No run manifest | `w3_runs` params, timestamp, completion status | Verified schema, CLI-run logic not live-tested |
| Temporal RAG news/social inputs | `collect_news.py`, `collect_external.py` exist | Preserved | Cross-week partial: publication/accessibility audit unresolved |
| Week 4 splits/filters | `build_dataset.py` uses `markets.outcome` | No Week 4 modifications | **Known critical dependency**: cannot consume current unverified outcomes |
| Week 5–7 evaluator/LLM/Jev/calibration | Not in upload | SQLite input contracts preserved | Not implemented here and not tested |

## Root causes, correctness issues and residual risks

1. **Critical, fixed for new collection:** `parse_market` inferred win/loss from `outcomePrices`. Prices are not independent ground truth, and `INSERT OR REPLACE` could overwrite previously reviewed fields. `parse_market` now sets unknown outcomes to NULL, while UPSERT never overwrites existing `outcome`.
2. **Critical, outstanding for old databases:** Existing `markets.outcome` values that came from earlier runs may already contain price-derived labels. This patch **does not silently delete data**. Quarantine these before Week 4; use `w2_resolution_checks` for labels after independent verification. Never treat `markets.outcome` as verified solely because it is non-NULL.
3. **High, improved:** Earlier price collection skipped the whole token if one sample already existed, leaving potentially incomplete ranges permanently. It now tracks completed `(token_id,start_ts,end_ts,fidelity)` windows and retries failed windows. Existing data from runs before this patch are **not automatically proven complete**.
4. **High, improved:** Invalid prices and response-shape failures previously entered storage or were mistaken for empty data. Price samples now require plausible range and timestamp. Errors are logged.
5. **High, partial:** Historical API series are sampled and may omit periods. Timestamp `t` is an observation timestamp, not a guarantee that the information was publicly accessible then. Do not use present market metadata as historical features.
6. **High, partial:** `/trades` is still the older offset-based endpoint, with depth caps, possible overlap and endpoint evolution. The newer Data API v2 uses cursor-based pagination and a different envelope. This patch explicitly rejects unexpected envelopes rather than silently corrupting data, but DOES NOT claim a complete trade census.
7. **High, partial:** `closed_ts` is not necessarily the verified information cutoff or final resolution timestamp. That logic belongs in `week2_spec.verify_resolution`, `week2_spec.audit_markets` and Week 4 construction.
8. **Medium, partial:** Selecting high-volume closed markets may introduce selection bias; the coverage report does not establish that a complete universe was sampled.
9. **Medium, outstanding:** Existing `collect_news.py` and `collect_external.py` are not changed. `seendate`, creation times and daily-bar dates may need availability-based embargoes for temporal RAG. Week 3 only provides archived request and market-price provenance.
10. **Medium, partial:** Prospectively captured `market_snapshots` have collection timestamps; they do not reconstruct the historical order book, spread, or liquidity before the collector was running.
11. **Medium, corrected:** max market count is honored within a fetched page; inputs reject nonpositive key limits. The older collector could overshoot.
12. **Medium, partial:** Dynamic pagination of a volume-sorted Gamma response can shift between requests; repeated crawl and cross-run reconciliation may be necessary.

## Files changed / added

- Modified `collect_polymarket.py`: `parse_market`, UPSERT, `collect_markets`, `collect_prices`, `collect_trades`, `snapshot_open`, CLI run status handling.
- Added `week3_pipeline.py`: `install`, `begin`, `finish`, `fail`, `request`, `validate_history`, `coverage`; new `w3_*` tables.
- Added `tests/test_week3_pipeline.py`: offline mocks/fixtures for labels, upserts, bounds, market limits, resume, trade empties, snapshots.
- Added `WEEK3_README.md` and this audit file.
- Retained all other Week 1–2 files unchanged.

## Verification performed

`python -m unittest discover -s tests -v`: **19 tests passed** (12 pre-existing and 7 new), isolated SQLite and synthetic API responses. `python -m compileall -q .`: Python source compilation passes. No live request to Gamma, CLOB or Data API has been made, and no resolved-market sample has been independently verified in this patch. Tests do not certify external uptime, endpoint schema or historical coverage.

## Acceptance conditions that remain open

- Execute a live smoke test on Gamma and CLOB; inspect returned response schemas, HTTP and JSON logs, and count actual market/price records.
- Validate old labels against independently archived rules and authoritative resolution evidence. Never use earlier price-inferred outcomes for supervised calibration.
- Validate Data API v1 legacy trade pagination or migrate to v2 with its cursor contract in a future scoped interface update before claiming full trade history.
- Assess per-market price gaps, coverage at all model prediction horizons and sampling bias.
- Verify and embargo timestamped news/social evidence before temporal RAG; prospective snapshots provide stronger access-time provenance than retrospective article timestamps.
- Correct `build_dataset.py` in Week 4 to select independently verified labels and strictly cutoff-safe metadata. Week 3 intentionally does not modify this later-week file.

**Conclusion:** The Week 3 infrastructure is patched and offline-tested; Week 3 historical data collection is **not empirically complete** until external integration and source verification are performed.
