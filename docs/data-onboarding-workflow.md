# Human-governed data onboarding

The repository separates flexible discovery from deterministic production execution.
SearchNode proposes predictor concepts. PredictorReviewNode freezes the human-approved
concept set. DataDiscoveryNode then uses an LLM with web search to propose official data
sources, while deterministic code independently checks the domain, retrieval URL, HTTP
response, content type, and sampled schema. A passing discovery produces only an
`unapproved` draft catalog entry. CatalogReviewNode is the only component that can create
a versioned approved catalog fragment, and it never mutates `config/data_catalog.yaml`.

## Review the SearchNode result

Create an editable submission:

```bash
.venv/bin/python scripts/init_predictor_review.py \
  --search-output outputs/my_search_test_4 \
  --output outputs/predictor_review_submission.json
```

Open the generated JSON. Replace every placeholder decision with exactly `approve`,
`reject`, or `request_revision`. Every approval requires `selection_rationale`; a rejection
or revision request requires `review_notes`. Then run:

```bash
.venv/bin/python scripts/review_predictors.py \
  --search-output outputs/my_search_test_4 \
  --submission outputs/predictor_review_submission.json \
  --output outputs/predictor_review_1
```

Discovery is blocked unless automated research validation passed, every candidate received
a decision, all approved candidates passed their research hard gates, and the approved set
retains primary coverage of every market in the approved scope. A successful review also
appends the approved IDs, roles, and human rationales to the project decision log.

## Run the SORA discovery slice

Use the exact approved predictor ID shown by the review command:

```bash
.venv/bin/python scripts/run_data_discovery.py \
  --predictor-review-output outputs/predictor_review_1 \
  --scope config/research_scope.example.json \
  --target three_month_compounded_sora \
  --provider gemini \
  --output outputs/sora_discovery_1
```

The agent may search and propose sources, metadata, schema mappings, and a structural
series classification. DataDiscovery v2 cannot propose aggregation, changes, lags,
interpolation, or missing-value rules.
The code then probes the proposed retrieval URL. A guessed endpoint, non-official host,
missing proposed field, unsupported format, or failed request does not pass the hard gate.
If only the deterministic profiler changes, re-run a saved proposal without spending another
LLM call using `scripts/reprobe_data_discovery.py`.

## Review the draft catalog

Create and edit a second human submission:

```bash
.venv/bin/python scripts/init_catalog_review.py \
  --discovery-output outputs/sora_discovery_1 \
  --catalog-version discovery-1 \
  --output outputs/catalog_review_submission.json

.venv/bin/python scripts/review_catalog.py \
  --discovery-output outputs/sora_discovery_1 \
  --submission outputs/catalog_review_submission.json \
  --output outputs/sora_catalog_review_1
```

The result is `approved_catalog_fragment.json`, not a production-catalog update. Promotion
into the production catalog remains a separate, explicit engineering step with adapter and
transformation tests. This prevents an LLM-discovered mapping from silently changing a
reproducible report.

## Preserve raw sources before mapping

After catalog approval, preserve the complete response without requiring a pre-existing
field mapping:

```bash
.venv/bin/python scripts/capture_unmapped_sources.py \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --output outputs/raw_portfolio_1
```

This produces immutable raw files and `raw_snapshot_evidence.json`. JSON, CSV, and Excel
are preserved before any date field, value field, sheet, or layout has been selected.

## Profile, map, execute, and repair

Run the isolated LangGraph Mapping Agent once for each approved source:

```bash
.venv/bin/python scripts/run_adaptive_mapping.py \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --raw-snapshot-evidence outputs/raw_portfolio_1/raw_snapshot_evidence.json \
  --source-id sora_singstat_datagov \
  --provider gemini \
  --max-attempts 3 \
  --output outputs/sora_mapping_1 \
  --print-summary
```

The deterministic SchemaProfiler records record paths, sheets, header rows, nested fields,
types, examples, and likely long/wide orientation. The LLM proposes only a typed Mapping
Contract. Code executes it against the complete snapshot and checks dates, values,
duplicates, missingness, coverage, and raw-to-mapped counts. Validation errors may be
returned for at most three mapping attempts. Exhaustion never weakens a check.

The mapping provider can be `gemini`, `openai`, `anthropic`, or `deepseek`. Mapping does not
perform web search, so DeepSeek does not require Tavily at this stage.

## Recommend and approve preparation operations

Pass the same preserved snapshots and validated mapping executions into the memory-aware
Preparation Advisor:

```bash
.venv/bin/python scripts/run_preparation_advisor.py \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --raw-snapshot-evidence outputs/raw_portfolio_1/raw_snapshot_evidence.json \
  --mapping-result outputs/sora_mapping_1/adaptive_mapping_result.json \
  --output outputs/sora_preparation_advice_1 \
  --print-summary

.venv/bin/python scripts/init_preparation_review.py \
  --advisor-output outputs/sora_preparation_advice_1 \
  --output outputs/preparation_review_submission.json

.venv/bin/python scripts/review_preparation.py \
  --advisor-output outputs/sora_preparation_advice_1 \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --submission outputs/preparation_review_submission.json \
  --output outputs/sora_preparation_review_1
```

Only `approved_preparation_plan.json` can proceed to final review. See
[`data-preparation-advisor.md`](data-preparation-advisor.md) for the operation rules.

## Unified review and Frozen Data Plan

The final Stage 2 review presents source metadata, raw checksums, validated mapping,
observed coverage, unit/frequency, and preparation choices in one table. The reviewer also
confirms the outcome/predictor/context and sale/rent/shared roles.

```bash
.venv/bin/python scripts/init_unified_review.py \
  --mapping-result outputs/sora_mapping_1/adaptive_mapping_result.json \
  --plan-id singapore_housing_plan \
  --as-of 2026-06-30 \
  --historical-start 2010-01-01 \
  --historical-end 2026-06-30 \
  --output outputs/unified_review_submission.json

# Edit every role and change confirmation_status from draft to confirmed before running
# the freeze command.

.venv/bin/python scripts/freeze_data_plan.py \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --raw-snapshot-evidence outputs/raw_portfolio_1/raw_snapshot_evidence.json \
  --mapping-result outputs/sora_mapping_1/adaptive_mapping_result.json \
  --preparation-plan outputs/sora_preparation_review_1/approved_preparation_plan.json \
  --review-submission outputs/unified_review_submission.json \
  --output outputs/frozen_plan_1 \
  --print-review
```

Only a confirmed review in which every mapping and preparation contract passes can create
`frozen_data_plan.json`. That file is the sole Stage 3 input.

## Current boundary

Automated tests cover JSON, CSV, and Excel profiling, bounded mapping repair, unified plan
freezing, and direct Stage 3 handoff. A live complete portfolio covering every final
predictor and both outcomes still needs to be run. Automatic fallback to another official
representation after all three mapping attempts is also pending; exhaustion currently
returns an explicit source-replacement decision to the user.
