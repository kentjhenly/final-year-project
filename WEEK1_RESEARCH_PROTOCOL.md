# Week 1 research protocol — version 1 (13 October 2026)

## Project goal
Test whether temporal retrieval and independently verified LLM forecasts add information beyond Polymarket YES prices in binary event forecasting, using supervised aggregation on held-out outcomes.

**Primary RQ:** Does a temporally grounded multi-agent LLM system aggregated with prediction-market probabilities improve out-of-sample binary probabilistic forecasting compared with market probability alone?

**RQ1:** Does timestamped retrieval improve independent LLM forecasts relative to no retrieval?
**RQ2:** Does independently checking retrieved evidence improve forecasts relative to a single agent?
**RQ3:** Does supervised aggregation outperform market price alone?
**RQ4:** Does supervised calibration improve reliability?

**Falsifiable hypotheses:** H1: RAG reduces mean Brier score relative to an otherwise identical no-RAG LLM. H2: verification reduces Brier score relative to the RAG-only agent. H3: aggregation reduces Brier score relative to market-only. H4: calibration improves reliability/calibration measured on a held-out test set. Null hypotheses are no improvement or worse performance.

## Literature matrix (foundational, not exhaustive)
| Research stream | Foundational reading | Application | Limitation / evaluation question |
| --- | --- | --- | --- |
| Prediction-market information aggregation | Wolfers & Zitzewitz (2004), *Prediction Markets* | market-price baseline | price may reflect liquidity/fees and is not ground truth |
| LLM forecasting | Halawi et al. (2024), *Approaching Human-Level Forecasting with Language Models* | structured, repeatable probabilistic predictions | unknown historical knowledge contamination |
| Retrieval augmentation | Lewis et al. (2020), *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* | timestamped evidence to forecasting agent | retrieval timestamps do not guarantee model ignorance |
| Multi-agent debate | Du et al. (2024), *Improving Factuality and Reasoning in Language Models through Multiagent Debate* | independent verifier / Jev veto | more agents can merely repeat bias; must ablate |
| Proper scoring | Brier (1950), *Verification of Forecasts Expressed in Terms of Probability* | primary scoring rule | account for dependence among same-event forecasts |
| Probability calibration | Niculescu-Mizil & Caruana (2005), *Predicting Good Probabilities with Supervised Learning* | calibration on past resolved events | requires disjoint fitting/evaluation periods |

**Gap (qualified):** Evaluate the incremental *out-of-sample* value of independently generated, verified and temporally grounded LLM forecasts above prediction-market prices, with explicit leakage controls. Novelty against post-2024 literature requires a separate current systematic search; no exclusivity claim is made.

## Frozen initial scope (subject to feasibility gate)
- Universe: binary YES/NO markets, initially economics and politics; specify inclusion/exclusion before results.
- Sample target: 300–500 independently resolved markets, contingent on auditable history.
- Prediction horizon: primary 7 days before known scheduled close; 1 day sensitivity if data supports it.
- Exclude real-money execution, active trading, multimodal inputs, training a foundation model, live production and broad market category coverage.
- Baselines: M0 timestamp-aligned market YES price, M1 regularized market-feature logistic regression, M2 LLM no retrieval, M3 temporal RAG LLM, M4 RAG + independent verifier/Jev, M5 market+M4 aggregation and calibrated variants.
- Metrics: per-market Brier (primary), log loss (clipped probabilities), reliability/calibration diagram, ECE as descriptive secondary statistic, bootstrap confidence intervals clustered by underlying event. Use common comparison subset; report exclusions.
- Temporal split: chronological by **label availability**, with distinct train/validation/test and event grouping. Do not fit models, calibrators or prompts on future resolutions. Markets for the same event must not straddle splits.
- Forecast outputs: market_id, event_id, forecast_ts, evidence item IDs and available_at timestamps, agent/model/version, raw p, verified p, market p, aggregate p, eventual outcome, outcome-known-at time, split, reproducibility metadata.
- Independent LLM must not receive contemporaneous market price. Jev acts as independent verification/veto/escalation, not the primary forecaster. Calibrator receives verified LLM and market features only after agent prediction is frozen.

## Feasibility and safety gates
1. Confirm Gamma market metadata and authoritative binary resolution; terminal market token prices alone are not trustworthy outcome labels.
2. Verify historical CLOB price observation timestamps and coverage near forecast time; expose missingness and staleness.
3. Record evidence `published_at`, `first_seen_at`, `retrieved_at`, and `available_at`; require `available_at <= forecast_ts`. Fetching retrospectively does not prove contemporaneous access.
4. Historic current-LLM forecasting is vulnerable to *parametric knowledge leakage*, even with RAG restricted to the past. Prefer prospective shadow forecasts or genuinely pre-event model checkpoints; label retrospective evaluation exploratory when not guaranteed.
5. Distinguish scheduled end, early closure, official resolution date and public outcome-known time. Do not define earlier forecasts from an outcome-dependent close timestamp.
6. Audit source availability and rate limits before committing to 300–500 markets. GDELT short lookback cannot supply arbitrary archival coverage.
7. No empirical hypothesis is accepted until held-out tests run. Document final exclusions, missingness and correlated events.

## Phase boundary
Week 1 produces research questions, hypotheses, literature matrix, scope, methodology, experiment contracts and a structural validator. The six uploaded scripts mostly implement Weeks 2–4 data collection/processing; this Week 1 package does not rewrite them. `week1_protocol.py` checks CSV structure only and explicitly cannot certify the historical information set or absence of outcome leakage.

## Execution
`python -m unittest discover -s tests -v`
`python week1_protocol.py --dataset research_dataset.csv --out week1_validation.json`

Exit code 0 on structural pass, 1 on failure. "STRUCTURAL_PASS_ONLY" is **not** a leakage-safe certificate.
