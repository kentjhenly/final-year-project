# Week 2 audit of original six-file FYP pipeline

## Scope and results
The six supplied Python source files (`common.py`, `collect_polymarket.py`, `collect_news.py`, `collect_external.py`, `build_dataset.py`, `week1_protocol.py`) were read from `FYP_Week1_Audit_and_Patch.zip` (which additionally contains Week 1 tests). The earlier Week 2 package (`api_probe.py`, `schema.sql`, `inspect_db.py`) was also read. This package retains all six source files byte-for-byte, adds `week2_spec.py`, and adds tests. It is an **incremental safety layer**, not a validated end-to-end Week 2 completion.

## Per-requirement acceptance matrix
| Original Week 2 subpoint | Existing implementation | Gap / status after patch |
|---|---|---|
| Gamma `/markets` discovery | `collect_polymarket.collect_markets` | Partial: filters resolved based on final price, no exhaustive exclusion audit; new `week2_spec.audit_markets` audits only markets already persisted. Rejected candidates lost upstream. |
| Gamma `/events` event grouping | `parse_market` picks first embedded event | Partial: event slug grouped, no actual `/events` paging, missing grouping fallback for linked events. |
| CLOB `/prices-history` | `collect_prices` chunks by period | Partial: drops retries if any price exists; not recording request payload / complete coverage; live endpoint not tested. |
| CLOB `/book` | no live order-book fetch | Missing: `snapshot_open` uses Gamma indicative outcomePrice, not bid/ask. |
| Data `/trades` | `collect_trades` | Partial: offset caps and missing-response issues; not independently verified. |
| News API / relevant evidence | `collect_news` using GDELT | Partial: stores GDELT `seendate` in misleading `published_ts`, not article version, not exact historical text. |
| Social and financial timestamps | `collect_external` | Partial: Reddit posts can be edited after creation; financial bar+1 day conservative but price availability not confirmed; optional week 2 scope. |
| Binary eligibility | `parse_market` | Partial: yes/no outcomes and tokens checked; no dispute/void/archival check. `week2_spec.selection` adds explicit provisional audit. |
| 30 pilot / 200–500 target | limit arguments | Unverified: no measured eligible count, no representative sampling. |
| Inclusion/exclusion audit | none in six files | Partial: `w2_selection` reasons for stored markets only, not all rejected Gamma candidates. |
| Independent resolution verification | final prices inferred | Missing live verification: `w2_resolution_checks` requires deliberate entry of source and archived rules; tests validate gating, not the external facts. |
| Event-based temporal split | `build_dataset` splits by resolution time | Partial/incorrect for correlated markets: same event across train and test; cutoff quantile by *row* allows weighting multi-horizon markets. |
| SQLite tables | `common.SCHEMA` | Partial: legacy schema lacks request/selection/versioned rule/audited cutoffs; nonbreaking additive `w2_*` schema supplied. |
| Raw response and request provenance | `markets.raw_json` only | Partial: `w2_raw_requests` defined but collectors not yet populating it. |
| UTC timestamp policy | `iso_to_ts`, unix ints | Partial: naive timestamps silently assumed UTC; first-seen news and market rules not versioned. |
| Forecast horizons 7/3/1 | `build_dataset` defaults 1/3/7/14 | Partial: Week 2 layer defaults 1/3/7, flags only verified cutoff anchor; legacy dataset still vulnerable. |
| Pre-cutoff price lookup | `build_dataset` filters <=T | Partially correct; rejects staleness, but inaccurate event cutoff can leak. New Week2 audit tests explicit cutoff and staleness. |
| No future articles or text | news/social count by timestamps | Partial: article version and first-seen vs publication not fully captured. Not safe to claim temporal RAG readiness. |
| Separate labels from model features | `build_dataset` includes outcome as evaluation column | Partial: must enforce feature allowlist in Week 6 agents; new resolution checks separated. |
| Forecast instance tables | legacy CSV output | Partial: SQLite forecast instances absent from existing six; prior Week 2 schema defines one but does not populate it. |
| Week 3 handoff / tests | Week1 tests | Partial: additional Week 2 unit tests provided; no real API, no 30-market integration run. |
| Overall D1–D4 compatibility | separate collectors and tabular datasets | Structural compatibility preserved: no original interfaces changed; downstream must explicitly query verified cutoffs and never rely on final-price-inferred labels. |

## Specific bugs / methodological issues
- `collect_polymarket.parse_market`: `outcomePrices` >= .99 used as resolution truth; market final price alone is not independently verified. Historical metadata may be revised. `collect_markets` silently discards excluded candidates before recording reasons and can exceed `max_markets` on last batch.
- `collect_polymarket.collect_prices`: existing one token price anywhere suppresses full history backfill. Failure after partial chunk does not record failed ranges; no raw endpoint provenance.
- `collect_polymarket.snapshot_open`: Gamma `outcomePrices` is not order-book bid/ask; timestamp is set before requests, potentially predating actual data retrieval.
- `collect_polymarket.collect_trades`: catches broad exceptions, offset depth / completeness not recorded; empty data and network failure can both result in missing trade coverage.
- `common.iso_to_ts`: assumes missing timezone is UTC rather than rejecting ambiguous timestamps; raw payload in `markets` overwritten on refresh.
- `collect_news.collect_news`: only market questions with already inferred outcome selected; `published_ts` actually means first GDELT seen; document text is not versioned; articles can be retrospective or edited.
- `collect_external.collect_social`: `created_utc` is not content's edit time, so text obtained retrospectively is not safe historical text. `collect_financial` uses bar+1 day as a conservative availability approximation but historic restatements possible.
- `build_dataset.build`: anchors on `closed_ts` or `end_ts` rather than verified information cutoff; split can put same-event markets on opposite sides; source document timing and market text are not point-in-time; `outcome` and price included in same CSV require downstream isolation.
- `week1_protocol.validate_rows`: structural validation is useful but cannot verify evidence authenticity or historic availability.
- Earlier `fyp_week2/api_probe.py`: uses final quote exactly 1/0 as label, limited first Gamma page, and one `interval=max` price request; stores request logs but not verified labels; standalone schema incompatible with existing Week1 DB.

## What this patch actually implements
`week2_spec.py`: additive schema for provisional selection, independent resolution checks, event grouping, forecast-cutoff price coverage and request-log table; report CSV; no claim that outside observations were verified. `tests/test_week2_spec.py`: synthetic tests for leakage boundary, stale prices, missing external verification, invalid outcomes, unverified-by-default.

## Explicitly open requirements / do not treat as complete
1. Live endpoint verification and controlled full pagination across Gamma markets/events, CLOB prices/book, optional Data trades.
2. Collector-level recording of **every** candidate rejection and every HTTP request/response into provenance tables (new table exists but has no producer in original collectors).
3. Independent rules archive, resolution verification and verified event information cutoff for each sampled market. `verify_resolution` is a manually invoked assertion and cannot validate truth by itself.
4. Historical news text snapshots, first-seen and content hashes needed for temporal RAG; retrospective API results alone cannot guarantee archived content.
5. Week 4+ integration: dataset builder must read only `w2_selection.verified=1` and use verified cutoffs/labels; event-grouped chronological splits must be enforced and tested in Week 4/5.
6. Week 3 pilot (30+ discovered candidates) with actual counts, failed calls, reproducible outputs and completeness diagnostics.

## Run
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python week2_spec.py --db polymarket_fyp.db --out week2_selection.csv
```
The default `week2_spec` flow only audits a **previously populated** Week 1 database; it does not make network requests or verify ground-truth resolution. For each verified case a researcher must manually corroborate official resolution, rule version and event knowledge cutoff, then invoke `verify_resolution` through Python. An archived rule version must be retained externally; `rules_archived=True` is a declaration, not automatic verification.
