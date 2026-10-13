# Week 3 runner (Python >=3.11)

Execute from this directory (`week2`), retaining import compatibility with Week 1–2.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Unix: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python collect_polymarket.py markets --db fyp.db --days-back 85 --min-volume 50000 --max-markets 10
python collect_polymarket.py prices --db fyp.db --fidelity 60 --chunk-days 14 --pre-days 90
python collect_polymarket.py trades --db fyp.db --max-per-market 500  # OPTIONAL, incomplete feed possible
python collect_polymarket.py snapshot --db fyp.db --min-volume 50000 --max-markets 10
python week3_pipeline.py --db fyp.db --out week3_coverage.json
python week2_spec.py --db fyp.db --out week2_selection.csv
```

`markets.outcome` is **not** inferred by this collector. Use the independent manual verification interface in `week2_spec.py` when authoritative outcome source and archived rules are available. Existing databases may contain legacy inferred labels; treat them as unverified until checked. `build_dataset.py` is not a leakage-safe downstream consumer until its Week 4 review is complete.

Data stays in the existing `markets`, `price_history`, `market_snapshots`, and `trades` tables. Week 3 adds `w3_runs`, `w3_requests`, `w3_errors`, `w3_windows`, `w3_trade_pages`, `w3_price_provenance`, `w3_snapshots`. Full JSON responses may contain large payloads: reserve storage and control retention. The current CLOB history is sampled, and `/trades` has an unverified legacy offset pagination contract. Collectors do not promise a complete historical reconstruction.

For temporal RAG and Jev, identify each piece of evidence by its observable availability time. An archived retrieval timestamp proves accessibility at collection time only, not earlier. Calibration and backtesting must split by market group/time and use verified labels from `w2_resolution_checks`, not unverified `markets.outcome`. For detailed requirements and open acceptance conditions see `WEEK3_AUDIT.md`.
