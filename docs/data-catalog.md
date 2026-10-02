# Data Catalogue

## Scope

The workflow covers Singapore's **private non-landed residential market**, primarily condominiums and private apartments. The two URA indices are market benchmarks used to describe sale-price and rental movements. Five conceptual predictors are selected in the literature review. The non-resident rental-demand factor uses two supporting data series, so the number of source series is greater than the number of conceptual predictors.

## Source Catalogue

| Role | Market | Indicator | Official source | Frequency | Unit | Transformation used in the report | Key limitation | Official webpage | API or download endpoint |
|---|---|---|---|---|---|---|---|---|---|
| Benchmark | Sale | URA Private Residential Property Price Index: Non-Landed | URA via data.gov.sg; dataset `d_97f8a2e995022d311c6c68cfda6d034c` | Quarterly | Index, 2009 Q1 = 100 | Filter `property_type = Non-Landed`; calculate QoQ and YoY percentage changes | An aggregate quality-adjusted index, not a transaction-price series | [Dataset page](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view) | [JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_97f8a2e995022d311c6c68cfda6d034c&limit=5000) |
| Benchmark | Rent | URA Private Residential Property Rental Index: Non-Landed, Whole Island | URA via data.gov.sg; dataset `d_8e4c50283fb7052a391dfb746a05c853` | Quarterly | Index, 2009 Q1 = 100 | Filter `property_type = Non-Landed` and `locality = Whole Island`; calculate QoQ and YoY percentage changes | Based on registered tenancy agreements; does not measure asking rents | [Dataset page](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view) | [JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_8e4c50283fb7052a391dfb746a05c853&limit=5000) |
| Predictor | Shared | Private residential pipeline supply | URA table `M400391`, accessed through its data.gov.sg mirror `d_055b6549444dedb341c50805d9682a41` | Quarterly | Dwelling units | Select total non-landed pipeline and relevant development-status series; report latest level, QoQ absolute change, YoY percentage change, and under-construction share | Pipeline units are not currently available stock; projects and completion timing may be revised; the official table excludes Executive Condominiums | [TableBuilder page](https://tablebuilder.singstat.gov.sg/table/TS/M400391), [dataset page](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) | [data.gov.sg JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_055b6549444dedb341c50805d9682a41&limit=500) |
| Predictor — structural measure | Rent | Non-resident rental demand: non-resident population | Singapore Department of Statistics table `M810001`, accessed through its data.gov.sg mirror `d_3d227e5d9fdec73f3bcadce671c333a6` | Annual, end-June | Persons | Select `Non-Resident Population`; calculate YoY percentage growth; retain annual frequency without quarterly interpolation | Not all non-residents rent private non-landed homes | [TableBuilder page](https://tablebuilder.singstat.gov.sg/table/TS/M810001), [dataset page](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view) | [data.gov.sg JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_3d227e5d9fdec73f3bcadce671c333a6&limit=500) |
| Predictor — timely signal | Rent | Non-resident rental demand: non-resident employment change | Ministry of Manpower Labour Market Report | Quarterly | Persons | Parse the configured 2Q 2026 final Labour Market Report, extract the current and previous quarterly changes in employed non-residents, and reject the report when its release date is after the reporting cut-off | This is employment data, not population data; it excludes non-working non-residents and includes workers who may live outside the private non-landed market; archive discovery is not automated | [Configured MOM report](https://stats.mom.gov.sg/Pages/Labour-Market-Report-2Q-2026.aspx) | Preserve the configured official HTML response and record its release date |
| Predictor | Rent | Private residential vacancy rate: Non-Landed | URA table `M400841`, accessed through its data.gov.sg mirror `d_01e3556fb916ca19a7e29fc39520fa78` | Quarterly | Derived percentage | Calculate `Vacant Non-Landed / Available Non-Landed × 100`; report QoQ and YoY percentage-point changes | Vacancy is inferred using utilities consumption and is not an advertised-listings measure; the official table excludes Executive Condominiums | [TableBuilder page](https://tablebuilder.singstat.gov.sg/table/TS/M400841), [dataset page](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view) | [data.gov.sg JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_01e3556fb916ca19a7e29fc39520fa78&limit=500) |
| Predictor | Sale | 3-month Compounded SORA | SingStat table `M700071`, accessed through data.gov.sg mirror `d_5fe5a4bb4a1ecc4d8a56a095832e2b24`; original source: Monetary Authority of Singapore | Monthly, end-of-period | Percent per annum | Select `Compounded Singapore Overnight Rate Average (SORA) - 3 Month`; use the final available month-end observation in each quarter; mark an incomplete quarter when the quarter-ending month is not yet available | This is a month-end financing-condition proxy, not a daily or quarterly average and not the mortgage rate paid by an individual borrower; the 3-month compounded series is unavailable for earlier periods before its publication | [SingStat table](https://tablebuilder.singstat.gov.sg/table/TS/M700071), [data.gov.sg dataset](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view), and [MAS methodology](https://www.mas.gov.sg/monetary-policy/SORA) | [data.gov.sg JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_5fe5a4bb4a1ecc4d8a56a095832e2b24&limit=500) |
| Predictor | Sale | Real GDP growth: Overall Economy | Singapore Department of Statistics table `M015631`, accessed through data.gov.sg mirror `d_a5ff719648a0e6d4b4c623ee383ab686` | Quarterly | Year-on-year percentage change | Select exact series `GDP In Chained (2015) Dollars`; use official YoY growth and calculate the change from the previous quarter in percentage points | Aggregate GDP is broader than household income, disposable income, or GDP per capita | [TableBuilder page](https://tablebuilder.singstat.gov.sg/table/TS/M015631), [dataset page](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view) | [data.gov.sg JSON API](https://data.gov.sg/api/action/datastore_search?resource_id=d_a5ff719648a0e6d4b4c623ee383ab686&limit=500) |

## API Families

The source catalogue requires two source adapters:

1. **data.gov.sg adapter** for the two URA benchmark indices and the official mirrors of five SingStat tables. It calls `GET https://data.gov.sg/api/action/datastore_search` with `resource_id`, paginates when necessary, reads observations from `result.records`, preserves `na` as missing rather than zero, and converts valid numeric strings explicitly. The public endpoint may return HTTP 429 when its unauthenticated request quota is exceeded, so retrieval must back off and surface a clear failure rather than silently reuse stale data.
2. **MOM report adapter** for quarterly non-resident employment change. It downloads the final-report edition configured in the catalogue, preserves the source HTML, extracts its release date, reference quarter, and published employment changes, and fails explicitly if the expected content cannot be found or if the report was released after the cut-off. It does not yet discover the correct historical edition from the MOM archive and must not silently substitute third-party data.

The annual population series and quarterly employment series must remain separate. Quarterly employment change is not used to interpolate or estimate quarterly non-resident population.

## Source-Specific Retrieval and Validation

### Quarterly non-resident employment change

The MOM report adapter records both the quarter described by the configured report and the report's publication date. For an as-of run, the observation is usable only when that report was released on or before the reporting cut-off. The raw HTML is stored before parsing. The normalized output contains `period`, `value`, `unit`, and `release_date`.

The current implementation does not reconcile total employment against resident and non-resident components, and it does not encode the migrant-domestic-worker coverage note as a structured field. These are documented extensions rather than completed checks. A missing label, ambiguous unit, or changed report wording produces a validation failure instead of an inferred value.

### 3-month Compounded SORA

The workflow retrieves the data.gov.sg mirror of SingStat table `M700071` and selects the exact series label `Compounded Singapore Overnight Rate Average (SORA) - 3 Month`. Because the official table reports end-of-month observations, the quarterly representation is the last available month-end observation in that quarter, normally March, June, September, or December. It is not described as a quarterly average.

If the quarter-ending month was not available by the reporting as-of date, the workflow may show the latest available month-end observation but must set `quarter_incomplete = true` and display its actual observation month. Values marked `na` remain missing. The MAS SORA page is retained as the methodology and cross-check reference, while SingStat is the machine-readable retrieval source.

## Per-Run Provenance Fields

The static catalogue above describes what each series means. Every workflow run should separately record the following operational fields:

| Field | Purpose |
|---|---|
| `source_id` | Stable internal name linking the run record to this catalogue |
| `reporting_as_of_date` | Cut-off date requested for the report |
| `latest_available_period` | Latest observation that existed on or before the cut-off date |
| `retrieved_at` | UTC timestamp at which the source was retrieved |
| `source_url` | Exact API or download URL used in that run |
| `http_status` | HTTP response status |
| `raw_snapshot_path` | Location of the preserved, unmodified source response |
| `raw_file_sha256` | Checksum proving which raw response produced the result |
| `freshness_status` | `current`, `stale`, `not_yet_released`, or `unavailable` under source-specific rules |
| `validation_status` | Result of schema, type, range, uniqueness, and period checks |
| `error_message` | Explicit failure reason when retrieval or validation does not succeed |

`latest_available_period` and `retrieved_at` must remain separate. The first describes the data observation; the second records when the workflow obtained it.
