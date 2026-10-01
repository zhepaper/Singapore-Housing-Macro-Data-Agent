# Agent Implementation Plan

**Project:** Singapore Housing Macro Data Agent  
**Scope:** Singapore private non-landed residential sale and rental markets  
**Last updated:** 1 October 2026

## 1. Objective

Build a reproducible LangGraph agent that retrieves official public data, preserves raw evidence, applies deterministic transformations, validates data quality and point-in-time constraints, and produces a concise analytical report whose numbers and claims can be traced to their sources.

The system is an evidence workflow, not a trained forecasting model. It identifies data that may be useful for predicting market changes but does not claim that its descriptive signals are forecasts or causal estimates.

## 2. Non-Goals

- Building a property-transaction database
- Training or evaluating a price-forecasting model
- Allowing an LLM to calculate indicators
- Allowing unrestricted web search during normal runs
- Replacing unavailable official data silently with third-party data
- Interpolating annual non-resident population into quarterly observations
- Treating quarterly non-resident employment change as population growth

## 3. Target Graph

```mermaid
flowchart LR
    A[Initialize run] --> B[Retrieve official sources]
    B --> C[Preserve raw snapshots]
    C --> D[Normalize observations]
    D --> E[Transform indicators]
    E --> F[Validate data and as-of rules]
    F -->|retryable failure| G[Bounded retry or official fallback]
    G --> B
    F -->|non-retryable failure| H[Halt with diagnostics]
    F -->|pass| I[Build evidence bundle]
    I --> J[Writer agent]
    J --> K[Deterministic verifier]
    K -->|fail| J
    K -->|pass| L[Final artifacts]
```

## 4. Engineering Principles

1. Deterministic code retrieves, parses, transforms, and validates data.
2. The LLM receives only validated evidence and writes prose; it does not create facts.
3. Every value must be traceable to a source URL, raw snapshot, retrieval timestamp, and SHA-256 checksum.
4. Observation period, official release date, retrieval time, and reporting cut-off remain separate.
5. Retries are bounded and based on error type; schema drift is never handled by guessing.
6. A failed required source prevents the report from being presented as current.
7. Each workflow run is immutable and resumable.

## 5. Implementation Phases

### Phase 0 — Freeze research scope

- [x] Define the property scope as private non-landed residential.
- [x] Separate the sale and rental markets.
- [x] Select URA non-landed price and rental indices as benchmarks.
- [x] Select the five conceptual predictors.
- [x] Document the literature-supported mechanisms and limitations.
- [x] Keep population and employment as separate measures.

**Exit criterion:** The agent does not reconsider the research scope or predictor set during normal runs.

### Phase 1 — Source catalogue and access spike

- [x] Define stable `source_id` values.
- [x] Record official pages and machine-readable endpoints.
- [x] Record exact series labels, selectors, units, and frequencies.
- [x] Test all eight source series against official endpoints.
- [x] Preserve successful and failed spike manifests.
- [x] Document direct SingStat failures and data.gov.sg mirrors.
- [x] Confirm MOM employment is report-based rather than a stable JSON series.

**Exit criterion:** Every required series has a verified official retrieval path or an explicit hard failure.

### Phase 2 — Agent foundation

- [ ] Install project dependencies in `.venv`.
- [ ] Compile and invoke a minimal LangGraph successfully.
- [x] Finalize the typed `AgentState` contract.
- [x] Add `run_id`, `reporting_as_of_date`, catalogue version, and prompt version to state.
- [x] Create an immutable per-run directory structure.
- [ ] Add checkpoint/resume support.
- [x] Define terminal statuses: `complete`, `partial`, `blocked`, and `failed`.

**Required artifacts:**

```text
runs/<run_id>/
  raw/
  normalized/
  metrics/
  report/
  run_manifest.json
  validation_report.json
```

**Exit criterion:** A minimal compiled graph starts, checkpoints state, resumes, and terminates with a structured run status.

### Phase 3 — Live retrieval tools

- [ ] Implement a data.gov.sg retrieval tool with pagination.
- [x] Implement the MOM final-report retrieval tool.
- [x] Restrict normal retrieval to approved official domains.
- [x] Add connect and read timeouts.
- [x] Add bounded retry for 429, 502, 503, and network timeouts.
- [x] Honour `Retry-After` when present.
- [x] Limit request concurrency to avoid public API quotas.
- [x] Save response content before parsing.
- [x] Record HTTP status, content type, retrieval time, byte count, and checksum.
- [x] Distinguish retryable network errors from non-retryable schema errors.
- [x] Never silently reuse an old snapshot as a new retrieval.

**Exit criterion:** A live run retrieves every source into a new run directory or returns explicit source-level diagnostics.

### Phase 4 — Normalization and transformation

- [x] Parse the data.gov.sg long-form URA benchmark format.
- [x] Parse the data.gov.sg wide SingStat-mirror format.
- [x] Parse current and previous non-resident employment changes from the MOM report.
- [x] Normalize annual, quarterly, and monthly period formats.
- [x] Preserve missing values as null rather than zero.
- [x] Calculate price-index and rental-index QoQ and YoY changes.
- [x] Calculate non-resident population YoY growth.
- [x] Calculate pipeline changes and under-construction share.
- [x] Derive private non-landed vacancy rate.
- [x] Select the final available monthly SORA observation in each quarter.
- [x] Mark incomplete SORA quarters.
- [x] Preserve GDP as official YoY growth and calculate the previous-quarter percentage-point change.
- [ ] Write normalized and derived records into the current run directory.
- [ ] Link each processed record to its source-run provenance.

**Exit criterion:** The same raw snapshot always produces the same normalized observations and metrics.

### Phase 5 — Quality gates and routing

- [x] Reject missing exact series labels.
- [x] Reject duplicate normalized series-period keys.
- [x] Reject ambiguous numeric strings.
- [x] Reject MOM reports released after the reporting cut-off.
- [x] Exclude observations whose period ends after the reporting cut-off.
- [ ] Check unexpected unit changes.
- [ ] Check invalid or missing periods.
- [ ] Check zero denominators before derived rates.
- [ ] Check record-count collapse and unexpected history truncation.
- [ ] Add source-specific freshness rules.
- [ ] Return `not_yet_released` separately from `failed`.
- [ ] Route retryable failures to bounded retry.
- [ ] Route schema drift and validation failures to human review.
- [ ] Document the limitation when historical release vintages are unavailable.

**Exit criterion:** The report node is unreachable whenever a required quality gate fails.

### Phase 6 — Evidence bundle

- [x] Define a whitelist of reportable series.
- [x] Prevent calculation inputs and intermediate rows from entering the report.
- [ ] Create one structured evidence object per reportable metric.
- [ ] Attach source URL, raw checksum, period, unit, derivation, and limitation.
- [ ] Attach the literature-supported mechanism separately from the current value.
- [ ] Classify evidence as `shared`, `rent`, or `sale`.
- [ ] Record whether the value is complete, provisional, stale, or unavailable.

**Exit criterion:** The evidence bundle alone is sufficient to reproduce and verify every quantitative report statement.

### Phase 7 — Writer agent

- [ ] Select the LLM provider through configuration rather than hard-coding it.
- [ ] Define structured writer input and output schemas.
- [ ] Provide only the validated evidence bundle and approved literature notes.
- [ ] Require separate shared, rental, and sale sections.
- [ ] Prohibit unsupported numbers, causal language, and model-forecast claims.
- [ ] Require explicit discussion of data limitations.
- [ ] Record model name, prompt version, token usage, and response timestamp.
- [ ] Provide a deterministic no-LLM report fallback.

**Exit criterion:** Replacing or disabling the LLM does not change any underlying value or validation outcome.

### Phase 8 — Verification agent and claim ledger

- [ ] Parse every quantitative claim from the draft.
- [ ] Match every reported value, unit, and period to the evidence bundle.
- [ ] Verify that every citation maps to the correct official source.
- [ ] Detect population/employment confusion.
- [ ] Detect sale/rent mechanism confusion.
- [ ] Detect missing incomplete-quarter or stale-data disclosures.
- [ ] Detect unsupported causal or forecasting language.
- [ ] Allow a bounded writer revision loop.
- [ ] Halt after the maximum revision count rather than loop indefinitely.
- [ ] Produce a machine-readable claim ledger.

**Exit criterion:** The final report has zero unmatched quantitative claims and zero unsupported citations.

### Phase 9 — Evaluation and failure testing

- [x] Add basic adapter, transformation, and workflow-node unit tests.
- [x] Test the as-of-date rejection of a future MOM release.
- [x] Test incomplete-quarter SORA handling.
- [ ] Add golden raw fixtures independent of live websites.
- [ ] Test HTTP 429 and `Retry-After` handling.
- [ ] Test HTTP 502/503 and timeout handling.
- [ ] Test a missing or renamed series.
- [ ] Test changed MOM report wording.
- [ ] Test unit changes and duplicate periods.
- [ ] Test `na`, zero denominator, and truncated history.
- [ ] Test report-number mismatch detection.
- [ ] Add one live integration test that is excluded from the default offline suite.

The first production-layer integration check was run manually on 1 October 2026: data.gov.sg succeeded, while MOM returned an explicit HTTP 403 diagnostic. An automated opt-in live test remains to be added.

**Exit criterion:** Both successful and expected-failure paths are covered, and live-source changes do not make the offline suite nondeterministic.

### Phase 10 — Submission packaging

- [ ] Generate one complete sample run.
- [ ] Include raw, normalized, metrics, manifest, validation, and report artifacts.
- [ ] Add installation and run commands to the README.
- [ ] Document architecture and design decisions.
- [ ] Document known limitations and future extensions.
- [ ] Verify that no API keys, credentials, caches, or personal files are committed.
- [ ] Run the complete offline test suite from a clean environment.
- [ ] Review the repository as an interviewer would.

**Exit criterion:** A reviewer can clone the repository, run the documented command, inspect the evidence chain, and understand all material design choices.

## 6. Immediate Next Work Session

Complete these tasks in order:

1. Resolve the project dependency installation and run `graph.compile().invoke()`.
2. Refine `WorkflowState` into the final `AgentState` and add run-level metadata.
3. Implement immutable run directories and a run-manifest writer.
4. Move retrieval from the separate spike script into a LangGraph retrieval node.
5. Add bounded retry and explicit error classification.
6. Run one live retrieval integration test.
7. Do not start the Writer Agent until the live retrieval graph passes.

## 7. Definition of Done

The agent is complete only when all of the following are true:

- [ ] A fresh live run succeeds through a compiled LangGraph.
- [ ] Every required official source is retrieved or explicitly marked unavailable.
- [ ] Raw responses and checksums are preserved.
- [ ] All normalized and derived values pass validation.
- [ ] As-of and release-date rules are enforced.
- [ ] The Writer Agent receives only validated evidence.
- [ ] Every quantitative claim passes deterministic verification.
- [ ] The run can be resumed without repeating successful work.
- [ ] Failure cases terminate cleanly without fabricated output.
- [ ] The repository passes its offline tests from a clean environment.
- [ ] The final report clearly distinguishes shared, rent-specific, and sale-specific mechanisms.

## 8. Progress Rule

At the end of each implementation session:

1. Update the checkboxes in this file.
2. Record any design decision that changes the graph or data contract.
3. Run the relevant tests.
4. Do not mark a phase complete until its exit criterion is satisfied.
5. Start the next session from the first unchecked item in the earliest incomplete phase.
