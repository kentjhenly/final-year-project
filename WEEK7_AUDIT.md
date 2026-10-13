# Week 7 audit, patch, and acceptance matrix

## Audited artifacts
- Uploaded `final-year-project-6.zip`: Week 1–6 code, Week 4 research dataset validation, Week 5 baselines and Week 6 lexical retrieval/forecast/verifier.
- Original `week7_forecasting_agent.zip`: `week7/agent.py`, `run_week7.py`, `tests.py`, example JSONL and README. The standalone package was NOT inside the uploaded Week 1–6 archive; audited separately and replaced by project-native `week7.py`.
- The Week 7 plan specified: Week 4/6 inputs, point-in-time prompts, independent probability with reasoning/uncertainty/IDs, validation, error logging/reproducibility, preliminary paired evaluation, executable tests and preparation for verification/calibration.

## Every originally specified deliverable and subpoint
| Requirement | Before patch | After patch / location | Verification |
|---|---|---|---|
| Read Week 4 observations | Missing: independent JSONL schema, no Week 4 CSV interface | `week7.run` calls `week5_baselines.load_dataset` | Integration test mocks dataset; actual CSV not supplied |
| Retrieve Week 6 evidence | Missing: manual JSONL evidence input | `week7.run` calls `week6.evidence_from_db` on SQLite with `strict=True` | SQLite integration test |
| Historical cutoff and available-at discipline | Partial: standalone agent checked `published_at` only, lacked fetched-at | `week6.evidence_from_db` enforces both seen/created and fetched; `week7.prepare` checks all 3 timestamps | Late-fetched and SQLite tests |
| Independent forecast, no market price | Partial: allowlist in standalone package, no project schema | `week7.prepare` only allows question, cutoff, horizon and filtered evidence | Prompt allowlist test |
| Avoid outcome leakage | Partial: prompt did not include explicit label, question revision unverified | `week7.prepare` does not serialize label/resolution; Week 4 input constraints remain | Unit test; historic question revision not provable |
| Forecast probability + rationale + uncertainty + IDs | Implemented in disconnected schema (`probability_yes`, `rationale`) | `week7.validate` uses Week 6-compatible `probability`, `reasoning`, `uncertainty`, `evidence_ids` | Parametric validation tests |
| Validate probability finite and in [0,1] | Partially covered in old code | `week7.validate` rejects bool, string, inf, NaN and out-of-range | Tests |
| Citation ID integrity | Partial; unknown IDs rejected, duplicates accepted | `week7.validate` rejects unknown/duplicate/non-string IDs | Tests; no faithfulness guarantee |
| Provider calls, retries, failure status | Partial: old calls lacked timeout and metadata | `provider_call`, `infer` timeout, retries, per-item errors, response/model/usage metadata | Mock tests only, provider not tested |
| Reproducible logs | Partial: isolated outputs did not map to Week 4 key | `week7.run` writes keyed JSONL and prompt SHA256, schema, source IDs, model, metadata | Integration test; provider weights/model revisions cannot be pinned here |
| Compare LLM vs market-only | Missing from executable original | `week7.run` reports market and LLM paired Brier/log loss on identical success rows | Synthetic mock integration test |
| Compare vs Week 5 logistic regression | Missing from executable original | **Still pending** separate join with Week 5 predictions on `(market_id,forecast_ts,horizon_days)`; explicitly documented and not misrepresented | Not tested / no baseline artifact provided |
| Forecast coverage and errors | Partial | `week7.run` reports prepared/completed/failed/coverage | Integration test |
| Train/validation/test isolation | Missing in standalone package | Week 5 `load_dataset` validates split chronology; `week7.run` defaults validation and gates test inference | Test gate; actual data not supplied |
| Week 8 Jev verification interoperability | Old output uses incompatible field names | Week 7 raw forecast keys match Week 6 response schema; Week 8 can take `forecast` plus identity | Schema-level compatibility only; actual Jev untested |
| Week 9 supervised aggregation | No calibration expected in Week 7 | Separate raw probability keyed with market ID/time/horizon; no labels in model context | Schema-level compatibility; calibration not implemented |
| Automated tests | Three tests for isolated package | `tests/test_week7.py`, plus complete Week 1–7 suite | 49 tests passed locally |
| README and runnable commands | Isolated JSONL instructions | This file includes project-native commands | CLI help + tests; real data/API not available |

## Bugs, methodological flaws, dependencies
1. Old `run_week7.py` accepted an incompatible JSONL schema (`cutoff_at`, `evidence`, `observation_id`) vs Week 4 CSV (`forecast_ts`, `event_group`, `split`) and Week 6 SQLite (`published_ts`, `fetched_at`). **Fixed with project-native runner.**
2. Old `week7.agent.build_messages` filtered by published time but not evidence **collection time**. Backfilled news is retrospective leakage. **Fixed by reusing strict Week 6 evidence selection and verifying timestamps in `prepare`.**
3. Old `Forecast` used `probability_yes` and `rationale` instead of Week 6 `probability` and `reasoning`. **Fixed schema.**
4. Old `run_week7.py` silently overwrote output on repeated invocation and did not compute comparison metrics. **Paired metrics implemented; output still overwrites intentionally, so supply a run-specific output directory and archive it.**
5. Retrieval by publication/first-seen/collection timestamps cannot prove old article text was not revised later; current SQLite news rows store headlines and GDELT seen times, not immutable web archives. **Unresolved upstream provenance limitation**; only observed-by-cutoff evidence can be used for strict inference.
6. Historical questions may have been edited after the cutoff, and model pretraining may contain future facts. **Cannot be eliminated by Week 7 prompt filtering**; require as-of question snapshots and prospective/frozen-model evaluation. Historical outputs should be labeled retrospective simulations.
7. Prompt-injection protection is instruction-level only, not a formal guarantee. Citation IDs verify membership but **not support for conclusions**.
8. No real Week 4 research dataset, collected SQLite database, API credentials or Week 5 per-row logistic predictions were supplied; numerical results and actual-provider compatibility remain **unverified**.
9. Week 6 already includes forecaster and verifier in `week6.run`. It is not modified; prefer the independent `week7.py` for Week 7. **Do not treat the Week 6 verifier as confirmed Jev.**
10. The default retrospective test split is gated with `--allow-test` to reduce accidental iteration on final holdout. Train/validation/test outcome separation derives from `week5_baselines.load_dataset`.

## Install and execute
From the extracted project root:

```bash
python -m pip install -r requirements.txt
python -m pip install 'openai>=1.0'  # only needed for live forecast calls
python -m pytest -q tests
python week7.py --input research_dataset.csv --db polymarket_fyp.db --mode prepare --split validation --output results/week7_prepare
# Configure OPENAI_API_KEY in the environment, then:
python week7.py --input research_dataset.csv --db polymarket_fyp.db --mode forecast --split validation --max-rows 20 --output results/week7_validation
```

Outputs: `week7_forecasts.jsonl` with individually keyed, validated independent raw forecasts (or per-row errors), and `week7_metrics.json` with coverage and paired market-vs-LLM metrics. To compare Week 5 logistic, join its per-observation predictions on the same compound key, compute all three metrics **on identical successful observations only**, and document excluded rows. Do not tune prompts on test results.

## Acceptance and evidence
- **Verified**: 49 offline tests passed in `python -m pytest -q tests` using Python in this workspace; SQLite/forecast integration used mocked responses.
- **Not verified**: end-to-end historical run with real CSV+database, third-party model endpoint and rate limits, actual Jev integration, Week 5 logistic comparison, or prospective predictive accuracy.
- **Out of Week 7 scope**: Jev verification agent implementation, supervised training/calibration, production scheduling/dashboard.
