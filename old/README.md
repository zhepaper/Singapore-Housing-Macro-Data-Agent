# Legacy compatibility workflow

This directory contains the original catalog-specific end-to-end workflow. It is retained
so the committed sample run can be reproduced and its historical implementation remains
reviewable. It is not the primary architecture for new sources.

The current design uses human-approved source mappings and preparation choices, freezes
them in a `FrozenDataPlan`, runs deterministic Stage 3 processing, and passes only validated
evidence to Stage 4 report generation.

Run the legacy snapshot workflow from the repository root:

```bash
.venv/bin/python old/run_workflow.py \
  --mode snapshots \
  --as-of 2026-10-01 \
  --output outputs/legacy-report.md
```

Shared retrieval, normalization primitives, source adapters, and observation models remain
in `src/housing_agent/` because both legacy and current workflows use them.
