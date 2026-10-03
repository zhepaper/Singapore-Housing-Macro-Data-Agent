# Project memory and decision governance

Project memory is a typed, versioned record of confirmed human decisions. It lets later
nodes understand the approved market scope, research preferences, analytical intent,
reporting style, predictor-selection rationale, and still-open questions without treating
the entire chat transcript as an instruction source.

## Source of truth

`config/project_memory.seed.jsonl` is an append-only decision log. Each line records the
actor, status, decision type, rationale, supporting reference, and any earlier event it
supersedes. Confirmed decisions enter the compiled snapshot; pending questions remain
visible but do not become approved policy. Secret-like fields are rejected by schema and
API keys must remain in the environment or the Git-ignored `.env` file.

Compile a reviewable snapshot with:

```bash
.venv/bin/python scripts/compile_project_memory.py \
  --decision-log config/project_memory.seed.jsonl \
  --output outputs/project_memory
```

The compiler writes `memory_v<version>.json` and `memory_manifest.json`. The manifest
contains a SHA-256 digest of the canonical snapshot. Memory compilation is deterministic:
the same decision log produces the same version and digest.

## How nodes use memory

- **SearchNode** reads confirmed scope and research preferences. It may use previous
  approvals as context, but it must research and validate a new proposal independently.
- **PredictorReviewNode** requires a human selection rationale for every approval and can
  append that approved decision to the log.
- **DataDiscoveryNode** finds and probes real official datasets and records their native
  structure. It does not turn a pending analytical choice into an approved operation.
- **DataPreparationAdvisorNode** reads memory, approved rationales, and verified data
  profiles before recommending alignment, change, lag, and missing-value rules. Human
  approval freezes those rules before deterministic execution and writes the decision back
  to memory.

This separation is deliberate: LLMs can research and explain choices, while production
calculations remain explicit, reviewable, and reproducible.

## Search traceability

Every SearchNode run persists `research_personalization.json` and records the memory
version and digest in `research_metadata.json`. A scope mismatch or changed snapshot with
an old digest fails closed. The search response schema contains source-frequency
requirements and rationale, but no aggregation, lag, interpolation, or missing-value
instruction.

## Predictor approval

The editable review template contains two different fields:

- `selection_rationale`: why an approved predictor belongs in the project.
- `review_notes`: why a candidate was rejected or needs revision, plus optional comments.

Running `scripts/review_predictors.py` appends an idempotent `predictor_approval` event to
the selected decision log only when the complete review passes. Re-running the identical
review does not duplicate the event.
