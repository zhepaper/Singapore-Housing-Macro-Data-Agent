# Normalized Data Contract

## Design rule

Raw responses are immutable evidence. Adapters convert them into a common long-form observation model, but do not overwrite, interpolate, or silently repair source values. Every processed dataset links back to a run manifest containing its exact URL, retrieval time, raw path, and SHA-256 checksum.

## Observation grain

One row represents one named series in one source period. Required fields are defined in `schemas/observation.schema.json`.

| Field | Meaning |
|---|---|
| `run_id` | Immutable workflow run that produced the persisted record |
| `provenance_id` | Join key from the record to its source entry in that run manifest |
| `source_id` | Stable source identifier from `config/data_catalog.yaml` |
| `series_id` | Stable normalized series name, independent of the provider's display label |
| `series_label` | Exact provider label retained for auditability |
| `period` | Canonical `YYYY-Qn`, `YYYY-MM`, or `YYYY` period |
| `frequency` | Native or explicitly derived frequency |
| `value` | Numeric observation; source missing values are `null`, never zero |
| `unit` | Unit before any interpretation |
| `market` | `sale`, `rent`, or `shared` |
| `role` | `benchmark`, `predictor`, or `derived` |
| `observation_status` | Whether the value was observed, missing at source, derived, or belongs to an incomplete quarter |
| `release_date` | Official release date when exposed by the source; otherwise `null` |
| `derivation` | Formula or selection rule for derived values; otherwise `null` |
| `source_periods` | Exact input periods used by a derived observation |
| `input_series_ids` | Exact normalized input series used by a derived observation |

## As-of-date rule

`reporting_as_of_date` is the information cut-off, not the retrieval timestamp. A report may use only an observation or official report that was publicly released on or before that date. `retrieved_at` records when the workflow downloaded the evidence and does not prove that the data existed at the earlier cut-off.

For sources that do not expose historical release dates, the workflow can reproduce the latest current dataset but must mark historical point-in-time availability as unverified. It must not claim a backtest free from look-ahead bias without archived vintages or documented release calendars.

## Frequency rules

- Quarterly URA benchmarks, pipeline supply, vacancy inputs, and GDP remain quarterly.
- Annual non-resident population remains annual and is never forward-filled or interpolated into invented quarterly observations.
- Quarterly non-resident employment change remains a separate employment-flow series.
- Monthly end-of-period 3-month Compounded SORA is represented quarterly only by selecting the last available month-end value in the quarter. The actual observation month is retained; a missing quarter-end month sets `quarter_incomplete = true`.

## Missing values and validation

Provider values such as `na`, blank strings, and non-numeric footnote markers become `null` with `observation_status = missing_at_source`. They do not become zero. A source fails validation when an expected series label disappears, periods are duplicated, period formats are invalid, numeric parsing is ambiguous, or a derived denominator is zero or missing. Lagged changes require exact calendar continuity: a missing quarter or year is not silently treated as the preceding period.

The run-level provenance contract is defined in `schemas/run-manifest.schema.json`, the reportable metric contract in `schemas/evidence.schema.json`, and writer boundaries in `schemas/writer-input.schema.json` and `schemas/writer-output.schema.json`. A partially successful run may produce diagnostics and raw snapshots, but the report-generation node must not describe a failed required source as current.
