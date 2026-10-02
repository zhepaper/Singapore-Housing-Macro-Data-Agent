# Singapore Private Non-Landed Housing Data Agent

## 1. Scope and objective

This project implements an auditable, agent-enabled workflow for public indicators that may be useful for predicting changes in Singapore's private non-landed residential sale prices and rents. The scope primarily covers condominiums and private apartments. It does not build a property-transaction database and does not train or claim a forecasting model.

The workflow treats the URA non-landed price and rental indices as outcome benchmarks. Five conceptual predictor groups are monitored:

- **Shared:** private non-landed pipeline supply.
- **Rental:** non-resident demand, represented separately by annual non-resident population stock and quarterly non-resident employment change; and the private non-landed vacancy rate.
- **Sale:** three-month Compounded SORA and real GDP growth.

Population and employment are deliberately not combined. Population is an annual end-June stock, whereas employment change is a quarterly flow and a timely proxy for one component of foreign-facing rental demand.

## 2. Why these indicators were selected

Pipeline supply is relevant to both markets because future completions can expand purchasable and rentable stock, although the effect may take several quarters or years. Non-resident population and employment are more directly connected to rental demand because many non-residents cannot purchase most residential property categories and may enter the tenant pool. Vacancy is a contemporaneous measure of rental-market tightness. SORA represents financing conditions that may affect mortgage affordability and leveraged sale demand. Real GDP growth is a broad activity measure that may affect income expectations, confidence, and purchasing capacity.

The mechanisms are hypotheses supported by the literature review, not estimated causal effects. The research basis and important differences between Singapore's public and private housing sectors are documented in [`docs/literature-review-and-indicator-selection.md`](docs/literature-review-and-indicator-selection.md).

## 3. Current descriptive signals

Using the packaged live official-source run retrieved on 2 October 2026 with an information cut-off of 1 October 2026:

- The URA private non-landed price index was **210.6 in 2026 Q2**, down **0.095% quarter-on-quarter** but up **1.838% year-on-year**.
- The URA private non-landed rental index was **162.5 in 2026 Q2**, up **0.371% quarter-on-quarter** and **1.753% year-on-year**.
- The non-landed pipeline contained **51,677 units**, up **3,566 units quarter-on-quarter** and **6.608% year-on-year**; **64.075%** of the pipeline was under construction.
- The non-resident population was **1,906,660 at end-June 2025**, up **2.730% year-on-year**. The configured MOM report recorded a **9,200-person increase in non-resident employment in 2026 Q2**. These remain distinct stock and flow measures.
- The derived private non-landed vacancy rate was **5.390% in 2026 Q2**, up **0.021 percentage points quarter-on-quarter** but down **1.486 percentage points year-on-year**.
- The latest SORA quarterly representation was **1.135% per annum for 2026 Q3**, using the July month-end observation. It is explicitly marked incomplete because the quarter-ending month was not yet present in the source snapshot.
- Official year-on-year real GDP growth was **5.9% in 2026 Q2**, **0.4 percentage points lower** than in the preceding quarter.

These observations are descriptive. Mixed directions across horizons are retained rather than collapsed into a single positive or negative signal.

## 4. End-to-end data processing

LangGraph controls the workflow sequence, while deterministic Python performs retrieval, parsing, calculation, validation, numeric rendering, and verification:

```text
official source
  -> immutable raw snapshot and checksum
  -> exact series selection
  -> period, number, unit, and label normalization
  -> information-cut-off filtering
  -> deterministic transformations
  -> quality and freshness validation
  -> evidence bundle with lineage
  -> constrained narrative writer
  -> deterministic claim verification
  -> report and run manifest
```

Every run stores the exact URL, retrieval timestamp, HTTP result, raw path, SHA-256 checksum, record count, latest available period, freshness status, and validation status. Derived observations also store the formula, input series identifiers, and exact source periods.

Lagged calculations use calendar periods rather than row positions. Quarter-on-quarter metrics require the actual preceding quarter, year-on-year quarterly metrics require the same quarter one year earlier, and annual growth requires the preceding year. Missing periods are not bridged. Annual population is not interpolated. Monthly SORA is represented by the last available month-end observation in each quarter and is labelled incomplete when the quarter-ending month is absent.

## 5. Reliability and failure handling

The workflow fails closed when a required source cannot be retrieved or parsed, an exact series disappears, a numeric value is ambiguous, units change, history collapses, periods are duplicated or malformed, a denominator is zero, freshness fails, or the writer/verifier contract is violated. A failed run preserves raw evidence and writes `failure_diagnostics.json`; it does not publish a report as current.

HTTP requests use an official-domain allowlist, bounded retries, rate limiting, and `Retry-After` handling. Cached official snapshots may be used only with an explicit command-line option, and such a run is labelled `partial` rather than `complete`.

The report writer never controls quantitative statements. The composer renders values directly from validated evidence and creates a claim ledger. The verifier checks every reported value, unit, period, source URL, and incomplete-quarter disclosure against that evidence.

## 6. Representative test and improvement

An engineering review identified a non-trivial lag bug: the initial transformation function used the previous non-missing row. If 2026 Q2 were absent, it could incorrectly compare 2026 Q3 with 2026 Q1 and label the result quarter-on-quarter. The implementation now converts periods to calendar ordinals and requires the exact lagged period. Tests cover missing quarters, missing years, and accidental comparisons across different series.

The same review found that a zero denominator in vacancy or pipeline calculations could raise an uncaught exception. Transformation errors are now converted into source-specific validation errors, routed through the LangGraph failure path, and persisted in diagnostics. A compiled-graph test confirms that this condition ends with a failed manifest instead of a traceback or fabricated report.

The offline suite additionally covers source adapters, missing labels, changed MOM wording, ambiguous and missing values, unit changes, duplicate periods, truncated history, freshness, incomplete SORA quarters, HTTP retry behavior, report tampering, checkpoint resume, schema conformance, and portable sample artifacts. A separate opt-in test checks current live endpoints.

## 7. Agent and LLM use disclosure

Codex was used during development to help structure the literature review, inspect official-source formats, draft and review code, generate tests, and identify reliability gaps. Its suggestions were checked against official source pages, preserved raw responses, deterministic calculations, and automated tests before inclusion.

The submitted sample report uses the default deterministic writer and requires no LLM credentials. An optional LangChain writer can produce only the qualitative narrative from a reduced view of already validated evidence. It cannot browse, select new indicators, calculate values, modify evidence, bypass failed validation, or write the quantitative evidence section. Its model name, prompt version, timestamp, and token usage are recorded when used.

## 8. Limitations

- Most data.gov.sg endpoints expose current-vintage history rather than archived release vintages. Period cut-offs are enforced, but historical point-in-time availability cannot be guaranteed where release dates are absent.
- The MOM adapter parses the final report edition configured in the catalogue. It validates that report's release date but does not automatically discover arbitrary historical report editions.
- Executive Condominium coverage is not identical across all URA series. The pipeline and vacancy tables exclude ECs, while the broader URA index methodology may include ECs depending on age and series coverage; comparisons therefore require caution.
- The indicators are aggregate. They do not represent every district, project, unit type, buyer, or tenant group.
- Predictor mechanisms and possible lags are not estimates of predictive accuracy or causality.

## 9. What I would add with two more weeks

1. Build an official-release archive so historical runs use true vintages and can support leakage-free backtesting.
2. Add dynamic MOM archive discovery, structured coverage notes, and reconciliation against published employment components where available.
3. Add CI for the complete offline suite and a scheduled, low-frequency live source health check.
4. Create a modelling layer separate from this evidence pipeline to compare lag structures and out-of-sample predictive value.
5. Evaluate whether comparable public data support responsible segmentation by market region or property type without turning the project into a transaction database.

## 10. Reproduction

Installation, offline and live run commands, optional LLM configuration, test commands, and artifact locations are provided in [`README.md`](README.md). The machine-readable source catalogue is in [`config/data_catalog.yaml`](config/data_catalog.yaml), and detailed system decisions are in [`docs/architecture.md`](docs/architecture.md), [`docs/data-contract.md`](docs/data-contract.md), and [`docs/limitations.md`](docs/limitations.md).
