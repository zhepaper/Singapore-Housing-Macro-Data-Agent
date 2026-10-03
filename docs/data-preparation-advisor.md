# Data Preparation Advisor

## Purpose

The DataPreparationAdvisorNode runs only after predictor approval, deterministic source
probing, and human catalog approval. It combines four kinds of evidence:

1. confirmed project memory and predictor-selection rationale;
2. the human-approved source definition, unit, native frequency, update frequency, and
   schema profile;
3. a newly downloaded raw response saved inside the advisor run, with retrieval time and
   SHA-256 checksum; and
4. the analytical goals recorded in memory.

It starts its human-facing output with one consolidated inventory table covering source,
raw snapshot, definition, unit, observation frequency, update frequency, observed raw
coverage, validation status, and recommended transformation. A short recommendation and
five review choices follow. It does not calculate values and its output is not executable
until a human confirms the exact contract.

## Separation of responsibilities

| Stage | Flexible LLM work | Deterministic work | Human gate |
|---|---|---|---|
| DataDiscovery | Find candidate official datasets and document structure | Probe URL and sampled schema | Approve source profile |
| PreparationAdvisor | Explain market use and recommend operations | Re-download and preserve raw bytes; validate source-level structure and contract semantics | Approve, edit, replace, customise, or reject |
| Preparation execution | None | Execute only an approved contract | Contract already approved |

DataDiscovery v2 contains `series_type` but no aggregation, target frequency, change
method, lag, interpolation, or missing-value instruction. Legacy discovery artifacts remain
readable, but their old transformation suggestions are discarded during migration.

## Contract rules

- Native observations are always retained.
- Monthly data may receive an additional quarterly `last`, `mean`, or `sum` view.
- Stocks, indices, and rates cannot be summed.
- Missing values remain null and interpolation is forbidden.
- Calendar lags are checked in code: monthly MoM=1, QoQ=3, YoY=12; quarterly QoQ=1,
  YoY=4; annual YoY=1.
- A predictive lag is optional, quarterly, explicitly exploratory, and never causal.
- Annual structural context cannot be assigned a quarterly predictive lag.
- Every recommendation must cite both a confirmed memory event and a verified source
  profile.

## Run the advisor

First produce one or more `approved_catalog_fragment.json` files through catalog review.
Then run:

```bash
.venv/bin/python scripts/run_preparation_advisor.py \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --output outputs/sora_preparation_advice_1 \
  --print-summary
```

The command first downloads every approved source into `<output>/raw/`. If any response
cannot be saved or cannot produce a preview for the approved series mapping, the node stops
before calling the LLM. The human-facing review is printed with `--print-summary` and saved
as `preparation_review.md`.

Create the editable review file:

```bash
.venv/bin/python scripts/init_preparation_review.py \
  --advisor-output outputs/sora_preparation_advice_1 \
  --plan-version preparation-1 \
  --output outputs/preparation_review_submission.json
```

Set `review_choice` to one of `approve_all`, `modify_transformations`, `replace_sources`,
`custom_instructions`, or `reject_proposal`. Free-text instructions are recorded under
`custom_instructions`; the corresponding explicit contract must be reviewed, and
`confirmation_status` must be changed from `draft` to `confirmed`. This is where a human
may replace `last` with `mean`, remove a predictive lag, or request revision. Review with:

```bash
.venv/bin/python scripts/review_preparation.py \
  --advisor-output outputs/sora_preparation_advice_1 \
  --catalog-fragment outputs/sora_catalog_review_1/approved_catalog_fragment.json \
  --submission outputs/preparation_review_submission.json \
  --output outputs/sora_preparation_review_1
```

Successful review writes `approved_preparation_plan.json` and appends an idempotent,
human-confirmed preparation event—including the selected option and any custom
instructions—to project memory.

The advisor validates one source at a time. Shared coverage, actual predictor–outcome
alignment, incomplete common quarters, staleness across series, and redundancy remain
post-retrieval validation tasks; the advisor does not claim those checks have passed.

## Deterministic execution

The execution command accepts normalized observation JSON and one approved contract:

```bash
.venv/bin/python scripts/execute_preparation.py \
  --observations path/to/normalized_observations.json \
  --approved-plan outputs/sora_preparation_review_1/approved_preparation_plan.json \
  --source-id sora_singstat_datagov \
  --output outputs/sora_prepared.json
```

The result contains native and explicitly labelled derived observations plus an execution
trace. No LLM is invoked during numerical execution.
