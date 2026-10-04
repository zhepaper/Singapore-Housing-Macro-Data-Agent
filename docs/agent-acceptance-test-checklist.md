# Agent Acceptance Test Checklist

This document is the single checklist for final end-to-end acceptance testing. Update it
whenever a workflow capability is implemented or retested. A checked item must have
repeatable evidence; implementation alone is not sufficient.

## Status meanings

- `[x] Passed`: implemented and verified by an automated or recorded live test.
- `[ ] Pending`: not implemented, not tested, or not yet demonstrated end to end.
- `Blocked`: implementation exists, but an external dependency currently prevents a live
  test. A blocked item remains unchecked.

## A. Research and predictor selection

- [x] SearchNode accepts a user-defined Singapore housing scope.
- [x] SearchNode returns literature-supported predictor concepts by requested category.
- [x] SearchNode separates sale, rent, and shared mechanisms.
- [x] SearchNode preserves citations and rejects unsupported evidence references.
- [x] Human predictor approval is required before source discovery.
- [x] Approved predictor rationales are written to project memory.
- [ ] Demonstrate one complete live SearchNode run with the final prompt and selected
  provider.
- [ ] Demonstrate that a user scope change routes back through predictor review.

## B. Data-source discovery and catalog review

- [x] DataDiscovery searches for official public sources without inventing endpoints.
- [x] Candidate URLs are independently probed.
- [x] Date, value, series-label, definition, unit, observation frequency, and update
  frequency fields are recorded.
- [x] Failed or non-official sources cannot pass the catalog gate.
- [x] Human catalog approval is required before preparation advice.
- [ ] Onboard and approve sources for every final predictor and outcome series.
- [ ] Demonstrate that a user source-replacement request routes back to DataDiscovery.

## C. Raw-first preparation advisor

- [x] Every approved source is downloaded again before preparation advice.
- [x] Raw response bytes are preserved.
- [x] Retrieval timestamp, HTTP status, byte count, and SHA-256 are recorded.
- [x] A raw-data preview is extracted from the approved series mapping.
- [x] Actual raw coverage and non-null observation count are extracted.
- [x] A failed raw capture stops the node before the LLM is called.
- [x] The human-facing output starts with one consolidated data inventory table.
- [x] The table retains definition, unit, observation frequency, and update frequency.
- [x] The output includes an assignment-requirements checklist.
- [x] The output includes a concise preparation recommendation.
- [x] The output offers approve, modify, replace-source, custom-instruction, and reject
  choices.
- [x] A confirmed modified contract passes deterministic semantic validation.
- [x] A draft or unconfirmed modification cannot be approved.
- [x] Approved choices and custom instructions are written to project memory.
- [ ] Run the final raw-first Advisor against Gemini and receive a complete structured
  recommendation. **Blocked on 2 October 2026 by Gemini monthly spending cap (HTTP 429).**
- [ ] Run the final Advisor with all selected predictor and outcome catalog fragments in
  one portfolio-level review.

### Recorded live raw-capture evidence

- Test date: 2 October 2026
- Source: official data.gov.sg SORA endpoint
- HTTP status: 200
- Bytes preserved: 77,680
- Observed coverage: 2005Oct–2026Jul
- Non-null observations: 250
- Evidence file:
  `outputs/sora_preparation_raw_first_live/raw_snapshot_evidence.json`

## D. Conversational preparation revision

- [ ] Implement `PreparationRevisionNode`.
- [ ] Accept a natural-language request such as “use quarter-end SORA instead of the
  quarterly mean”.
- [ ] Convert the request into a schema-valid proposed contract without changing raw facts.
- [ ] Show a human-readable before/after diff.
- [ ] Explain the analytical effect of the requested change concisely.
- [ ] Pause with `awaiting_human_confirmation` after presenting the diff.
- [ ] Require explicit confirmation before freezing the revised contract.
- [ ] Allow the user to revise again or restore the recommended default.
- [ ] Route a source change to DataDiscovery rather than changing the API inside the
  preparation node.
- [ ] Route a predictor or market-scope change to SearchNode and Predictor Review.
- [ ] Bound invalid LLM revision attempts and fail closed.

## E. Adaptive source-to-recommendation integration

This is the current critical integration gap. The entire data-review segment is **not**
missing: raw capture and the preparation recommendation already exist, and source review
and preparation review exist as separate gates. The missing capability is the adaptive
bridge that lets those implemented components accept a previously unseen raw-data
structure.

### Recorded integration concern — 3 October 2026

The deterministic Stage 3 processing node is implemented and tested. Its completion must
not be confused with completion of the end-to-end handoff. Stage 3 deliberately requires
an already approved `FrozenDataPlan`, including valid Mapping Contracts, Preparation
Contracts, raw snapshot paths, and checksums. The original concern was upstream of Stage 3:

```text
Previously unseen raw structure
→ generate and execute a proposed Mapping Contract
→ repair the mapping from deterministic validation feedback when necessary
→ obtain unified human approval
→ freeze source + mapping + preparation contracts
→ pass the FrozenDataPlan to the completed Stage 3 processor
```

The bridge is now implemented and covered by offline JSON, CSV, Excel, repair, freeze, and
Stage 3 handoff tests. The remaining acceptance risk is operational: it has not yet been
demonstrated live across the complete final portfolio using a genuinely new official
source. Automatic fallback to a second official representation after three failed mapping
attempts also remains pending.

Concern-specific acceptance tests:

- [ ] Use a previously unseen official JSON, CSV, or Excel structure as the test input.
- [x] Generate a Mapping Contract from the preserved raw snapshot without manually adding
  its field names to production code.
- [x] Execute the proposed mapping and return deterministic field-, date-, value-, and
  reconciliation errors to the mapping component.
- [x] Demonstrate a successful bounded mapping repair after an intentionally incorrect
  first proposal.
- [x] Freeze the approved source, Mapping Contract, Preparation Contract, snapshot path,
  and SHA-256 into one `FrozenDataPlan`.
- [x] Pass that exact plan directly into the Stage 3 processing interface without manual edits.
- [x] Confirm Stage 3 produces `validated_evidence_bundle.json` for the newly onboarded
  source.
- [x] Confirm the report stage reads that evidence bundle rather than recalculating from
  raw data.

Current status:

| Capability | Status |
|---|---|
| Preserve and profile a raw snapshot | Implemented and tested |
| Generate a preparation recommendation from an approved mapping | Implemented and tested |
| Review the source and preparation contract separately | Implemented and tested |
| Generate a mapping from a previously unseen raw structure | Implemented and tested offline |
| Execute and validate an approved generic mapping | Implemented and tested for JSON, CSV, and Excel |
| Repair an invalid mapping from deterministic error feedback | Implemented; maximum three attempts |
| Try another official representation or source when mapping cannot be recovered | Pending |
| Combine source, mapping, and preparation approval into one user review | Implemented and tested |
| Feed a newly approved mapping into the production normalization workflow | Implemented and tested through FrozenDataPlan handoff |

Final acceptance checks:

- [ ] Give the workflow a predictor whose official source format is not already represented
  by a source-specific production adapter.
- [ ] Download and preserve the new raw response without manually adding field names to the
  production code.
- [x] Generate a typed mapping contract from a deterministically profiled raw structure.
- [x] Execute the proposed mapping against the complete preserved snapshot.
- [x] Reconcile raw and parsed record counts and report invalid dates, values, duplicates,
  and observed coverage.
- [x] Feed a deliberately incorrect mapping back to the mapping component and demonstrate a
  successful bounded repair.
- [ ] Demonstrate fallback from a failed API representation to an official CSV or Excel
  representation of the same dataset.
- [ ] Demonstrate that a definition-changing source or predictor substitution requires
  explicit user approval.
- [x] Pass the validated mapping execution into the existing data-plan recommendation
  without reimplementing the recommendation logic.
- [x] Present source, raw evidence, mapping, and transformation recommendation in one human
  review.
- [x] Freeze the approved source, mapping, and preparation contracts together.
- [x] Normalize the unseen source through the production workflow using the frozen mapping.
- [x] Confirm that no unsupported format is silently ignored and no field, unit, definition,
  or observation is guessed.

## F. Retrieval, normalization, and deterministic transformation

- [x] Production retrieval preserves raw source files and checksums.
- [x] Normalization rejects unknown schema, series labels, dates, and numeric formats.
- [x] Missing values are not silently converted to zero.
- [x] Native-frequency observations are preserved.
- [x] Approved monthly-to-quarterly transformations are deterministic.
- [x] Rates cannot be summed across a quarter.
- [x] Annual data are not interpolated into artificial quarterly observations.
- [x] Calendar-aligned changes do not bridge missing periods.
- [x] Incomplete quarters follow the approved reject or partial-period policy.
- [x] Frozen plans, raw paths, and SHA-256 values are verified before processing.
- [x] Generic approved mappings normalize JSON, CSV, and Excel long/wide layouts.
- [x] After-as-of observations are preserved but excluded from calculations.
- [x] Stage 3 writes deterministic normalized, transformed, validation, lineage, and
  evidence artifacts.
- [x] Repeated runs with identical plans and snapshots are byte-identical.
- [ ] Execute every final approved preparation contract against newly retrieved raw data.
- [ ] Confirm that each transformed value retains lineage to its raw observations.

## G. Post-retrieval and cross-series validation

- [x] Verify the actual common time range across outcomes and predictors.
- [x] Enforce the reporting as-of date using release availability, not only observation
  period.
- [x] Exclude or label incomplete latest quarters.
- [x] Confirm genuine consecutive months and quarters before applying lags.
- [x] Confirm predictor–outcome period alignment.
- [x] Check missingness and usable observation counts after alignment.
- [x] Check staleness against each series' approved tolerance.
- [x] Flag highly redundant predictors without automatically deleting them.
- [x] Confirm that annual contextual series are not presented as timely quarterly signals.
- [x] Persist a machine-readable validation report and stop report generation on hard
  failures.

## H. Report generation and verification

- [x] Deterministic numeric evidence is separated from LLM-written qualitative prose.
- [x] Unledgered or altered numeric claims fail verification.
- [x] Sale and rental mechanisms are kept distinct.
- [x] Unsupported causal or forecasting language is rejected.
- [x] Report revision attempts are bounded.
- [ ] Generate the final report from the complete newly approved portfolio.
- [x] Confirm every reported number, unit, period, and source against the evidence bundle.
- [x] Confirm that the report discloses as-of limitations, incomplete periods, and source
  vintage limitations.
- [ ] Complete a reviewer walkthrough from user scope to final report without manual code
  edits.

## I. Portability, safety, and reviewer handoff

- [x] API keys are loaded from environment variables and are not printed by provider-status
  commands.
- [x] Offline automated tests run without live API credentials.
- [x] A complete sample run is portable and checksum-valid.
- [ ] Clone the repository into a clean directory and follow only the README.
- [ ] Run the full workflow on a second machine or clean environment.
- [ ] Confirm that no API key, `.env`, personal path, or private data is committed.
- [ ] Confirm that all user-facing commands work from the repository root.
- [ ] Conduct a final interviewer-style architecture and failure-mode review.

## Current automated baseline

Last recorded on 4 October 2026:

```text
180 tests passed in the full regression checkpoint
11 Stage 4 acceptance tests passed across targeted final-change runs
1 optional live-source test skipped as designed
Snapshot end-to-end workflow completed with 8 sources, 2,012 observations,
1,846 derived observations, and no validation errors
```

## J. Final submission integration audit

- [x] Make the FrozenDataPlan-driven Stage 3 path, rather than the legacy catalog-specific
  workflow, the documented primary end-to-end command.
- [x] Produce one reviewer-ready FrozenDataPlan covering every final predictor and both
  sale and rental outcome benchmarks.
- [x] Run that frozen plan over preserved raw snapshots and pass its validated evidence
  bundle directly to Stage 4.
- [x] Confirm that SORA's incomplete-quarter policy is explicitly human-approved in the
  frozen plan; do not rely only on the legacy catalog default.
- [x] Regenerate the committed sample report from the FrozenDataPlan-driven run and verify
  every claim against lineage and raw checksums.
- [x] Move the legacy catalog-specific entrypoint and orchestration modules under `old/`
  and `housing_agent.legacy`, clearly labelled as a compatibility demo.
- [x] Replace the legacy GitHub Actions command with the FrozenDataPlan-driven wrapper
  after the current Stages 2–4 are integrated.
- [x] Document the observed local Ollama limitation: `qwen3:4b` timed out on the strict
  ResearchProposal schema, even when generation was split by factor category.
- [x] Keep Ollama optional unless a complete live SearchNode run passes; the required
  snapshot reproduction path must not depend on an LLM or search API.

Run the offline suite:

```bash
cd /path/to/Singapore-Housing-Macro-Data-Agent
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Run the raw-first Advisor after provider quota is available:

```bash
.venv/bin/python scripts/run_preparation_advisor.py \
  --catalog-fragment outputs/sora_catalog_review_3/approved_catalog_fragment.json \
  --output outputs/sora_preparation_acceptance_test \
  --print-summary
```

For a final portfolio test, repeat `--catalog-fragment` once for every approved predictor
and outcome source.
