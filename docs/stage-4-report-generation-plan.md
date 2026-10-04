# Stage 4: Evidence-Bound Report Generation

## Objective

Stage 4 converts the immutable `ValidatedEvidenceBundle` produced by Stage 3 into a
concise, auditable applied social-science report. Code controls what the report may claim.
An optional LLM controls the organisation, interpretation, transitions, and calibrated
academic language around immutable evidence anchors.

The stage never retrieves data, remaps a source, changes a transformation, or calculates a
new statistic. Any such change must return to the appropriate earlier workflow stage.

## Boundary

Stage 4 may start only when:

- Stage 3 completed successfully;
- the evidence bundle passes its Pydantic contract;
- cross-series validation did not fail; and
- the reporting as-of date is present.

Stage 4 succeeds only when the final Markdown and its claim ledger pass deterministic
verification. An unverified draft is never labelled final.

## Subgraph

```mermaid
flowchart LR
    A[ValidatedEvidenceBundle] --> B[Evidence Selector]
    C[Optional Report Brief] --> D[Context Builder]
    B --> D
    D --> E[Prompt Builder]
    E --> F[Writer]
    F --> G[Report Composer]
    G --> H[Claim Verifier]
    H -->|pass| I[Report Packager]
    H -->|fail and attempts remain| J[Revision Prompt]
    J --> F
    H -->|fail after three attempts| K[Blocked Draft and Diagnostics]
```

## Deterministic evidence selection

For each reportable series, the selector takes the latest eligible, non-null observation.
It excludes predictive-lag views because their period is an outcome-alignment period rather
than the source observation period. It retains approved levels, quarterly comparison views,
and changes as separate claims. Claim identifiers are stable for identical evidence.

Each selected claim retains:

- series and source identifiers;
- label, market role, and portfolio role;
- value, unit, period, and observation frequency;
- derivation and input periods where applicable;
- raw snapshot checksum and raw-record reference; and
- any applicable data-quality disclosure.

## Report context and prompt

The context builder combines selected evidence with an optional human-approved report brief.
The brief may contain scope wording, the user objective, predictor mechanisms, literature
references, source-page records, and reporting preferences. It cannot add quantitative
evidence. When a compiled `MemorySnapshot` and `FrozenDataPlan` are supplied, a deterministic
bridge carries the confirmed scope, report style, and predictor-selection rationales into the
brief. The plan maps memory predictor IDs to the final source and series IDs; memory never
overrides evidence values.

The prompt instructs the writer to produce continuous prose under Introduction, Data and
Analytical Approach, Rental-Market Findings, Sale-Market Findings, Limitations,
and Conclusion. Each findings section must proceed from outcome to predictors to a qualified
synthesis. The writer may place only supplied `{{CLAIM:...}}` and `{{LIT:...}}` anchors; it
may not copy numbers, invent citations, expose workflow internals, claim causality, or add an
unsupported outlook.

The prompt text, prompt version, evidence checksum, provider, model, and response metadata
are persisted.

## Numeric claims and report composition

All numerical sentences are rendered deterministically from selected claim anchors. The LLM
sees the structured evidence so it can organise a substantive argument, but it cannot type,
round, calculate, or modify a value. Monthly native observations are omitted from report
selection when an approved quarterly comparison view exists, avoiding duplicate evidence
while retaining the native series in Stage 3 artifacts.

The final report contains only the market analysis, its prose methodology, limitations,
data sources, and references. Mapping contracts, checksums, claim ledgers, prompts, and
lineage remain in companion artifacts rather than interrupting the reader-facing report.

## Verification and recovery

Deterministic verification checks:

- every evidence anchor occurs exactly once and resolves to an approved claim;
- every rendered evidence sentence exactly matches the claim ledger;
- numerical text outside deterministic evidence or literature rendering is rejected;
- the as-of date and academic sections are present;
- prohibited causal and forecasting phrases are absent;
- source and literature records are retained; and
- causal, forecast, proxy, frequency, and timing boundaries are disclosed.

On failure, the writer receives only the verifier errors and the already approved context.
The complete draft may be revised at most three times. Continued failure produces a blocked
draft and machine-readable diagnostics for human review.

## Artifacts

```text
report/
├── final_report.md                 # only after verification passes
├── blocked_report.md               # only after bounded failure
├── selected_evidence.json
├── report_context.json
├── report_prompt.txt
├── report_prompt_manifest.json
├── prompts/                         # every bounded draft prompt
├── claim_ledger.json
├── verification_report.json
├── source_register.json
├── writer_metadata.json
└── run_manifest.json
```

## Acceptance tests

- consume the Stage 3 bundle directly;
- reject an altered value, unit, period, or source;
- reject unledgered numeric prose;
- reject unsupported causal or forecasting language;
- preserve sale/rent/shared distinctions;
- disclose incomplete or excluded evidence and as-of limitations;
- stop after three failed drafts;
- produce a deterministic no-key fallback report; and
- complete a Stage 3 to Stage 4 integration test without reading raw data.
