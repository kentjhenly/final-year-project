# Week 6 audit and acceptance matrix

## Scope and integration
Audited original `week6_temporal_rag/week6.py` and README against the actual Week 1–5 archive. The original Week 6 script was **not included** in `final-year-project-5.zip`; this patch adds a Week 6 module, tests and documentation to that project. Week 1–5 modules remain unchanged.

| Original item | Original status | Patched status / evidence |
| --- | --- | --- |
| Temporal timestamp filtering | Partial: published/first-seen CSV checks, disconnected from SQLite schema | `evidence_from_db` applies creation/GDELT-seen plus `fetched_at <= forecast_ts` in strict mode; tests |
| Historic evidence RAG | Partial: simple title/body lexical ranking | `evidence_from_db` deterministic market-scoped news/social retrieval and overlap ranking; semantic retrieval **not implemented** |
| Evidence relevance and citations | Partial | ID-ranked evidence, safe allowlisted prompt and checked citation IDs in `validate_response`; semantic accuracy **not verified** |
| Independent LLM estimate | Partial: OpenAI only; incompatible input columns | `model_payload`, `make_prompt`, `call_model`, `validate_response`; Week 4-compatible; real API **untested** |
| No price/outcome in model context | Partial: allowlisted primary, verifier included full first response | Explicitly allowlisted primary and verifier payload, tests; external news may itself contain outcome claims and is not independently fact checked |
| Jev verification | Missing: same model was used | Two configurable clients/backends; actual Jev connectivity **not verified or claimed** |
| Forecast logs | Partial: prompts/hash and partial model responses, no native IDs | `run` stores stable identity, prompt hash, evidence, models, results and errors; API metadata/versions beyond model names **not captured** |
| Error handling | Partial | Per-row exceptions preserved with partial initial response; no automatic retries or resumed runs |
| Paired Brier/log loss | Incorrect: market/raw/verified individually scored on different subsets and Brier clipped | `score` and `run` require identical verified-success rows; Brier original probabilities, clipped log loss |
| Week 4 split isolation | Missing: first N rows, no split validation | `load_dataset` and explicit validation/test/train split; no calibration/tuning is performed |
| Backfilled evidence governance | Incorrect: example separate CSV ignored project fetched-at provenance | Strict excludes late fetch; `--allow-exploratory` explicitly warns and enables late fetch |
| Week 5 compatibility | Missing | imports Week 5 validation and uses Week 4 field names; no modifications to baseline outputs |
| Week 7 supervised calibration | Out of Week 6 scope | Identity + independent raw and verified probabilities logged for future join; no supervised fitting |
| Reproducible testing | Missing | `tests/test_week6.py`; local deterministic tests; no provider/live database trial |
| Scheduled orchestration | Not implemented in original | Not implemented; later-week orchestration dependency, not falsely claimed |

## Methodological caveats
- `news.published_ts` in this project's schema is **GDELT first-seen**, not actual article publication. Retrieval enforces its timestamp and `fetched_at`. Publisher release time and content revision history remain unverifiable from collected columns.
- `social_posts.created_ts` does **not** prove when historic text was accessible. Strict mode also requires `fetched_at <= forecast_ts`.
- The news collector stores only headline, not article body. No semantic embeddings, source credibility model, or archived article content are present; this is lexical, market-scoped headline RAG.
- Raw current-market descriptions and resolution details are not forwarded to prompts; only the Week 4 captured question is forwarded. Event/question revisions still depend on Week 4 snapshot provenance.
- Historical forecast reconstruction using models trained after the forecast timestamp is a **retrospective simulation**, not a genuine ex-ante deployment. Model internal knowledge may include future facts. Strict timestamps on retrieved documents alone cannot prove absence of model parametric knowledge leakage. Historical backtests should be labeled exploratory unless using time-appropriate frozen model checkpoints or prospective collection.
- The model response can hallucinate undisclosed information; cited ID validation ensures identifiers exist, **not** evidential faithfulness. Human checks remain necessary.
- `test` is intended for one-time frozen evaluation. Do not iterate model/prompt choices based on it. Related questions can evade Week 4 `event_group` grouping; inspect clustering.
- Model calls require provider access, billing and provider support for JSON mode. Jev has no verified API contract here. Configure `--verifier-base-url`, `--verifier-model`, `--verifier-key-env` only if Jev actually exposes a compatible endpoint; otherwise treat this as a generic verifier, not Jev.

## Run
`python -m pip install -r requirements.txt && python -m pip install openai>=1.0` (OpenAI only needed for forecast mode).

`python -m pytest -q tests/test_week6.py`

`python week6.py --input research_dataset.csv --db polymarket_fyp.db --mode prepare --split validation --output results/week6`

`python week6.py --input research_dataset.csv --db polymarket_fyp.db --mode forecast --split validation --max-rows 20 --model gpt-4.1-mini --verifier-model gpt-4.1-mini`

Do not interpret prepare-mode zero scores as experimental outcomes; use paired forecast-mode rows. The project contains no user-provided research data, API keys, or live model results for an end-to-end empirical evaluation.
