# Singapore Housing Macro Data Agent

An auditable LangGraph workflow for public indicators that may help explain changes in Singapore's **private non-landed residential** sale and rental markets. It retrieves official data, preserves raw evidence, performs deterministic transformations and quality checks, and generates a concise verified report. It is an evidence workflow, not a trained forecasting model or a property-transaction database.

## Research scope

- **Shared:** private non-landed residential pipeline supply
- **Rental:** annual non-resident population stock, quarterly non-resident employment change, and private non-landed vacancy
- **Sale:** 3-month Compounded SORA and real GDP growth
- **Benchmarks:** URA private non-landed price and rental indices

Population and employment are deliberately separate: population is an annual stock; employment change is a quarterly flow and a higher-frequency proxy for one part of non-resident demand.

## Quick start

Python 3.11 or later is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,llm]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Run in GitHub without local setup

The repository includes a manually triggered GitHub Actions workflow, so a reviewer can run the agent entirely in the browser:

1. Open the repository's **Actions** tab.
2. Select **Run Housing Data Agent**.
3. Click **Run workflow**, enter the reporting as-of date, and choose `snapshots` or `live`.
4. Open the completed workflow run to read the report in the job summary.
5. Download the `housing-agent-report-<date>` artifact for the report and complete run audit trail.

`snapshots` is the recommended reproducible demonstration and requires no API key. `live` retrieves the configured official public sources and may fail if a public endpoint is temporarily unavailable. The optional OpenAI writer is intentionally not used by this browser workflow, so no repository secret is required.

Run a fully offline, reproducible workflow over preserved official snapshots:

```bash
.venv/bin/python scripts/run_workflow.py \
  --mode snapshots \
  --as-of 2026-10-01 \
  --output outputs/report.md
```

Run against the official live endpoints. Requests are serial and rate-limited by default:

```bash
.venv/bin/python scripts/run_workflow.py \
  --mode live \
  --as-of 2026-10-01 \
  --output outputs/live-report.md
```

Cached fallback is never silent. It must be explicitly enabled; a run that uses it is labelled `partial` and the report includes an operational warning:

```bash
.venv/bin/python scripts/run_workflow.py \
  --mode live \
  --as-of 2026-10-01 \
  --allow-cached-fallback
```

The deterministic writer is the default and requires no API key. To use the optional LangChain OpenAI writer, set `OPENAI_API_KEY` outside the repository and pass `--writer openai`; all quantitative evidence remains deterministic and is verified after drafting.

## Outputs and audit trail

Each run creates `runs/<run_id>/` with raw responses, checksums, normalized observations, derived metrics, checkpoints, an evidence bundle, a claim ledger, verification results, and the final report. Resume an interrupted running workflow with:

```bash
.venv/bin/python scripts/run_workflow.py \
  --as-of 2026-10-01 \
  --resume-run-id <run_id>
```

[`sample_run/`](sample_run/) is a complete live run captured on 2 October 2026: all eight official sources returned HTTP 200, all quality gates passed, and every quantitative report statement passed deterministic verification.

## Tests

The default suite is offline and deterministic. The live endpoint smoke test is opt-in:

```bash
RUN_LIVE_TESTS=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_live_sources -v
```

Start with [`SUBMISSION_REPORT.md`](SUBMISSION_REPORT.md) for the concise analytical and engineering summary. Supporting detail is in [`docs/architecture.md`](docs/architecture.md), [`docs/data-catalog.md`](docs/data-catalog.md), [`docs/data-contract.md`](docs/data-contract.md), [`docs/literature-review-and-indicator-selection.md`](docs/literature-review-and-indicator-selection.md), and [`docs/limitations.md`](docs/limitations.md).
