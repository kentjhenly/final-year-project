# Week 1 audit against the six uploaded files (13 October 2026)

Status terminology: **fully** = implemented and checked here; **partial** = present but insufficient; **missing** = absent; **incorrect** = contradicts required research protocol.

## Every Week 1 item

| Original plan subpoint | Uploaded implementation | Status | Week 1 remediation |
| --- | --- | --- | --- |
| Goal: incremental forecasting value beyond Polymarket | Only collectors and CSV dataset, no research protocol | Missing | `WEEK1_RESEARCH_PROTOCOL.md` |
| Primary research question | None | Missing | research protocol |
| RQ1 temporal RAG benefit | `news`, `social_posts` columns in `common.py`, count features in `build_dataset.py`; no retrieval experiments | Partial | specify M2 vs M3, evidence contract |
| RQ2 verification agent | None | Missing (Week 6/7 dependency) | specify M3 vs M4, verifier/Jev interface |
| RQ3 market+LLM aggregation | `market_price` only; no LLM probabilities or fitting | Missing (later weeks) | specify M4 vs M5 |
| RQ4 probability calibration | None | Missing (later weeks) | specify validation-only calibration |
| H1-H4 falsifiable hypotheses | None | Missing | hypotheses in research protocol |
| Background and problem statement | Not code deliverable | Missing | research protocol goal and gap; prior narrative may be used in report |
| Literature: markets | None | Missing | Wolfers & Zitzewitz literature matrix |
| Literature: LLM forecasting | None | Missing | Halawi et al. literature matrix |
| Literature: RAG | None | Missing | Lewis et al. literature matrix |
| Literature: agent verification | None | Missing | Du et al. literature matrix |
| Literature: scoring/calibration | None | Missing | Brier, Niculescu-Mizil & Caruana matrix |
| Qualified literature gap | None | Missing | caveated gap statement |
| Freeze binary YES/NO and category scope | `parse_market` filters YES/NO but no reliable category enforcement | Partial | explicit universe in protocol; filter later |
| Sample target 300–500 | CLI 500 for markets, 300 for news/social; no coverage gate | Partial | feasibility conditional target |
| 7-day primary, 1-day secondary | default horizons `[1,3,7,14]`, no designation | Partial | primary/secondary horizons in protocol |
| Real-money trading etc exclusions | No execution code, exclusions undocumented | Partial | exclusions in protocol |
| M0 market price | `build_dataset.py` market_price feature | Partial (not scored) | evaluation specification |
| M1 logistic baseline | No model | Missing (Week 5) | evaluation specification |
| M2 no-retrieval LLM | No model | Missing (Week 6) | evaluation specification |
| M3 temporal RAG | news counts only, no retrieval contents on agent | Missing (Week 6) | evidence contract |
| M4 verification/Jev | None | Missing (Week 6/7) | verification spec |
| M5 supervised aggregation | None | Missing (Week 7) | aggregation spec |
| Brier primary, log loss and calibration | None | Missing (Week 5+) | metrics plan |
| Temporal held-out train/test | `build_dataset.py` resolution quantile split | Incorrect for chronological label availability and group events | protocol + structural validator; defer pipeline edit Week 4 |
| No market-price anchoring for LLM | No agents | Missing (Week 6) | separation contract |
| Evidence as-of timestamp | `published_ts`, `created_ts` filtered to <=T for counts | Partial, not sufficient | timestamps contract + feasibility gates |
| Output reproducibility/logging | `fetched_at` in schema; no agent logs | Partial | output contract |
| Scope + feasibility review | no documented review | Missing | feasibility gates, supervisor approval still pending |
| Week 1 report and final review | no report | Missing | research protocol produced; supervisor validation pending |

## File/function-specific issues (not silently fixed outside Week 1)

- `collect_polymarket.py:parse_market`: **critical** labels inferred from `outcomePrices` near 0/1 and `closedTime` used as `resolve_ts`; extreme price is not authoritative resolution and early closes can be outcome dependent. Store authoritative resolved outcome and public label-known time separately.
- `collect_polymarket.py:collect_markets`: Gamma filters `end_date_min/max`, which may not select actually resolved within dates; `closed=true` alone is not an authoritative resolution guarantee. `parse_market` can keep `market_id='None'` or null question if malformed.
- `collect_polymarket.py:snapshot_open`: `INSERT OR REPLACE` replaces `markets` row with unresolved snapshot and can erase previously verified outcome on repeated runs; `outcomePrices` is snapshot market indication, not necessarily executable orderbook bid/ask. Recorded timestamp is collector time, useful for prospective data only.
- `collect_polymarket.py:collect_prices`: excludes a token as soon as *any* point exists, so partial failure can make a permanently incomplete price history. `/prices-history` API response/retention is not verified live here.
- `collect_polymarket.py:collect_trades`: `offset` bounds and Data API history are not validated; fails/openly partial with no completeness indicator.
- `collect_news.py:collect_news`: **confirmed SQL defect**: `news` table has **10** columns in `common.SCHEMA` but `INSERT OR IGNORE INTO news VALUES (?,?,?,?,?,?,?,?,?)` provides **9** placeholders (tuple itself contains nine values). SQLite raises `table news has 10 columns but 9 values were supplied`. Intended schema needs separate declared field mapping or added column.
- `collect_news.py:collect_news`: skips already-populated markets despite incomplete collection; marks a failed window as complete by moving `t=t2`; lack of HTTP `raise_for_status`; no pagination for results above `maxrecords=250`; `seendate` is *first indexed*, not validated `published_at`; current GDELT availability insufficient for older history.
- `collect_external.py:collect_social`: Reddit post `created_utc` may be invalid/missing (fallback zero), score/comments observed later are **not** valid historical values. Search results are incomplete/unverified and not marked so. `INSERT OR IGNORE` prevents retroactive repairs.
- `collect_external.py:collect_financial`: assigning daily bar availability at UTC midnight + 1 day is only a heuristic, not actual release time; no provenance or exchange timezone. The market data download may be revised or adjusted.
- `build_dataset.py:build`: `closed_ts` chosen as resolution timestamp but may be a non-scheduled early closure or non-label-availability time; timestamp `T=closed_ts-h*DAY` leaks knowledge of future event duration even with price/history filtered. Use predeclared forecast schedules and independent label-known-at timestamps.
- `build_dataset.py:build`: uses `price_history` filtered by ts correctly in principle but does not verify the observation-time semantics, token type and missingness. More serious: `news_count` and `social_count` rely on `published_ts`/`created_ts`, not retrospectively proven `available_at`; later-fetched Reddit engagement is post-outcome information if used.
- `build_dataset.py:build`: split by per-row resolution quantile; repeated horizons can yield correlated rows; correlated events across separate markets are not grouped; resolution labels could be available after training cutoff. There is no validation partition or prospective embargo for labels. Null, extreme, duplicate and stale edge cases not fully validated.
- `build_dataset.py:build`: financial index close lag +1 day is conservative for some US assets, insufficient for others and cannot establish historical point-in-time revision control. Output omits group/event identity and observed-at provenance.
- `common.py:SCHEMA`: news insert/schema mismatch above; missing evidence available_at, authoritative resolution and label-known-at, event group ID, model run audit logs, source and completeness metadata. Data model upgrade should be in Weeks 2–4 migration, not disguised as Week 1 research work.
- `common.py:iso_to_ts`: silently treats naive timestamps as UTC, which should be explicit in ingestion provenance.
- `requirements(2).txt`: lower bounds only; lacks reproducible lockfile; `yfinance` remote behavior may change. Runtime dependencies for future agent/Jev/calibration weeks not declared and should not be invented now.

## Changes made in this Week 1 patch

**New files only:** `WEEK1_RESEARCH_PROTOCOL.md`, `week1_protocol.py`, `tests/test_week1_protocol.py`, `AUDIT.md`. Original six files are included unmodified and renamed to their intended canonical script names in the package for convenience; they are **not** asserted working. The validator tests logical integrity of CSV fields, probability range, split consistency and duplicates; it does not validate data provenance or LLM knowledge.

**Gates not verified:** live Polymarket/GDELT/Reddit endpoints, market-label correctness, sufficient historical data, prospective time-safe retrieval, any agent/model performance, Jev interface, supervisor acceptance. These are pending later-week implementations/evaluation.
