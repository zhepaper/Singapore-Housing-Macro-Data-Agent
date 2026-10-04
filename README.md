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

Run the complete reviewer-facing workflow from the approved data plan to a verified report:

```bash
.venv/bin/python scripts/run_submission_pipeline.py \
  --output outputs/submission_run \
  --print-report
```

This command is offline, deterministic, and requires no API key. It verifies every raw
snapshot checksum, normalizes and validates all eight series, applies only the approved
transformations, writes a validated evidence bundle, and generates a claim-checked report.
The Stage 3 policy registry restricts aggregation, change, and derived-series operations to
approved methods. For example, the vacancy rate is calculated inside Stage 3 directly from
the official vacant and available non-landed rows, with both inputs and the ratio formula
recorded in lineage; it is not read from a precomputed analytical file.
The included plan uses an information cut-off of **2026-10-01** and excludes observations
outside its approved historical window. To use a different cut-off or series selection,
complete the discovery/review stages and freeze a new approved plan rather than silently
editing a finished run.

## Run in GitHub without local setup

The repository includes a manually triggered GitHub Actions workflow, so a reviewer can run the agent entirely in the browser:

1. Open the repository's **Actions** tab.
2. Select **Run Housing Data Agent**.
3. Click **Run workflow**.
4. Open the completed workflow run to read the report in the job summary.
5. Download the `housing-agent-submission-run` artifact for the report and complete audit trail.

The browser run uses the preserved official snapshots and approved frozen plan, so it is
reproducible and requires no API key. LLM-backed research and prose are optional; the
reviewer-critical numerical path and deterministic report do not depend on a paid service.

The earlier monolithic implementation is retained only for compatibility and comparison.
Run it with:

```bash
.venv/bin/python old/run_workflow.py \
  --mode snapshots \
  --as-of 2026-10-01 \
  --output outputs/report.md
```

Run the same legacy compatibility pipeline against the official live endpoints. Requests
are serial and rate-limited by default:

```bash
.venv/bin/python old/run_workflow.py \
  --mode live \
  --as-of 2026-10-01 \
  --output outputs/live-report.md
```

Cached fallback is never silent. It must be explicitly enabled; a run that uses it is labelled `partial` and the report includes an operational warning:

```bash
.venv/bin/python old/run_workflow.py \
  --mode live \
  --as-of 2026-10-01 \
  --allow-cached-fallback
```

The deterministic writer is the default and requires no API key. To use the optional LangChain OpenAI writer, set `OPENAI_API_KEY` outside the repository and pass `--writer openai`; all quantitative evidence remains deterministic and is verified after drafting.

## Optional predictor-research node

Before source discovery and catalog freezing, an isolated LangGraph SearchNode can research candidate predictors for a human-approved scope. It supports Gemini, OpenAI/ChatGPT, Anthropic/Claude, DeepSeek, Groq, and local Ollama. The node reads a compiled, human-governed project memory so it retains scope and preferences across stages. This step proposes literature-backed predictor concepts and source-frequency requirements; it does not choose aggregation, lag, interpolation, missing-value treatment, production endpoints, or approved predictors.

Check the available providers and required environment variables:

```bash
.venv/bin/python scripts/run_research_search.py --list-providers
```

Create a local `.env` file from the safe template, then add the key for the provider you want to use:

```bash
cp .env.example .env
```

For Gemini, edit `.env` so that the relevant line contains your Google AI Studio key:

```dotenv
GEMINI_API_KEY=your_key_here
```

Then run the node:

```bash
.venv/bin/python scripts/run_research_search.py \
  --provider gemini \
  --request "Identify publicly accessible predictors for Singapore private residential sale prices and rents."
```

Use `--provider openai`, `--provider anthropic`, `--provider deepseek`, `--provider groq`, or `--provider ollama` to select another provider. DeepSeek, Groq, and Ollama use Tavily for the auditable web-search trace and therefore require `TAVILY_API_KEY`; Groq additionally requires `GROQ_API_KEY`. Ollama runs the synthesis model locally, requires no model-provider key, and defaults to `qwen3:4b` at `http://127.0.0.1:11434`. Install and start Ollama, then run `ollama pull qwen3:4b` before selecting it. The CLI loads `.env` from the repository root, while variables explicitly set in the calling shell take precedence. `.env` is Git-ignored and must never be committed. Detailed scope, validation, and output rules are documented in [`docs/search-node-review.md`](docs/search-node-review.md); memory and decision governance are documented in [`docs/project-memory.md`](docs/project-memory.md).

Ollama is an optional local fallback, not the reviewer-critical path. The strict research
schema is generation-intensive and may time out on resource-constrained machines. The
packaged snapshot workflow and deterministic report regeneration do not require Ollama,
Tavily, or any model-provider API.

SearchNode output does not enter production automatically. The human-governed onboarding
path now supports predictor approval, bounded Gemini source discovery, independent official
URL probing, versioned catalog-fragment approval, pre-mapping raw preservation, deterministic
JSON/CSV/Excel schema profiling, multi-provider Mapping Contracts, bounded mapping repair,
memory-aware preparation advice, unified approval, FrozenDataPlan creation, and deterministic
Stage 3 execution. Start with
[`docs/data-onboarding-workflow.md`](docs/data-onboarding-workflow.md). Discovery artifacts
remain drafts and never overwrite `config/data_catalog.yaml`.

Add `--print-summary` to print a citation-rich academic synthesis after a successful live run. To render an existing run without calling an API again:

```bash
.venv/bin/python scripts/show_research_search.py \
  --output outputs/my_search_test
```

## Outputs and audit trail

The formal submission command creates `outputs/submission_run/stage3/` and `stage4/` with
the frozen plan, normalized and excluded observations, transformations, lineage, validation
results, evidence bundle, report prompt, claim ledger, verification result, and final report.
[`sample_run/submission/`](sample_run/submission/) is a committed successful run.

The preserved legacy workflow creates `runs/<run_id>/`. Resume an interrupted legacy run with:

```bash
.venv/bin/python old/run_workflow.py \
  --as-of 2026-10-01 \
  --resume-run-id <run_id>
```

[`sample_run/raw/`](sample_run/raw/) contains the official snapshots captured on 2 October
2026. Their checksums are pinned in the frozen plan. The current submission run passes the
Stage 3 data gates and Stage 4 claim verification; its two timing warnings disclose that the
Q1/Q2 non-resident employment releases were not available at the corresponding quarter ends.

## Tests

The default suite is offline and deterministic. The live endpoint smoke test is opt-in:

```bash
RUN_LIVE_TESTS=1 PYTHONPATH=src .venv/bin/python -m unittest tests.test_live_sources -v
```

Start with [`SUBMISSION_REPORT.md`](SUBMISSION_REPORT.md) for the concise analytical and engineering summary. Supporting detail is in [`docs/architecture.md`](docs/architecture.md), [`docs/data-catalog.md`](docs/data-catalog.md), [`docs/data-contract.md`](docs/data-contract.md), [`docs/literature-review-and-indicator-selection.md`](docs/literature-review-and-indicator-selection.md), and [`docs/limitations.md`](docs/limitations.md).

## Generate a report from Stage 3 evidence

The new Stage 4 LangGraph reads `validated_evidence_bundle.json` directly. It does not read
raw snapshots or recalculate metrics. The default writer is deterministic and requires no
API key:

```bash
.venv/bin/python scripts/run_stage4_report.py \
  --evidence outputs/stage3/evidence/validated_evidence_bundle.json \
  --brief config/report_brief.example.json \
  --output outputs/stage4 \
  --provider deterministic \
  --print-report
```

Add `--memory <compiled-memory.json> --plan <frozen-data-plan.json>` to carry the confirmed
scope, reporting style, and predictor-selection rationale forward from the earlier stages.
The plan is used only to map predictor IDs to final source and series IDs; numeric evidence
still comes exclusively from the validated evidence bundle.

The optional brief supplies scope wording, predictor rationales, literature identifiers,
and source links; it cannot add numeric evidence. Use `--provider gemini`, `openai`,
`anthropic`, `deepseek`, `groq`, or `ollama` for LLM-written qualitative prose. Ollama
requires no API key and defaults to the local `qwen3:4b` model. All values, periods, units,
lineage, and citations remain deterministically rendered and verified. A failed draft is
revised at most three times and is otherwise saved as `blocked_report.md`, never as a final
report. See [`docs/stage-4-report-generation-plan.md`](docs/stage-4-report-generation-plan.md).
