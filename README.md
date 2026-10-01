# Singapore Housing Macro Data Agent

An auditable LangGraph workflow that retrieves and analyses public indicators relevant to Singapore's private non-landed residential sale and rental markets. The project focuses on predictor data and descriptive market signals; it does not build a property-transaction database or claim to produce a trained forecasting model.

## Current indicator set

- Shared: private non-landed residential pipeline supply
- Rent: non-resident rental demand (annual population plus quarterly employment change) and private non-landed vacancy
- Sale: 3-month Compounded SORA and real GDP growth
- Benchmarks: URA private non-landed price and rental indices

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
```

Run the official-source access check:

```bash
.venv/bin/python scripts/spike_sources.py
```

Run the LangGraph over preserved snapshots:

```bash
.venv/bin/python scripts/run_workflow.py --as-of 2026-10-01 --output outputs/report.md
```

The source catalogue is JSON-compatible YAML so the access spike can run with the Python standard library before dependencies are installed. See `docs/data-catalog.md`, `docs/data-contract.md`, and `docs/architecture.md` for selection, provenance, and graph-design details.
