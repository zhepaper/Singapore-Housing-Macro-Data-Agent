# Singapore Private Non-Landed Housing Indicator Brief

**Information cut-off:** 2026-10-01

## Scope

This report monitors Singapore's private non-landed residential sale and rental markets. It presents descriptive public-data signals, not causal estimates or model forecasts. The sale and rental indices are outcome benchmarks; the remaining series are candidate predictors.

The workflow preserves mixed frequencies: annual population is not interpolated, quarterly series remain quarterly, and monthly SORA is represented by the last available month-end observation in each quarter.

## Indicator definitions and mechanisms

| Indicator | Market | Definition | Observation / update frequency | Mechanism and potential lag |
|---|---|---|---|---|
| **Non-resident population** (`SingStat M810001; Non-Resident Population`) | Rent | Singapore non-resident population stock measured at end-June. | annual end june / annual | Growth in the non-resident population may expand the foreign-facing tenant base. Structural rental-demand measure; effects may appear contemporaneously or over subsequent quarters, but the annual series does not identify a quarterly lag. |
| **Non-resident employment change** (`MOM Labour Market Report 2Q 2026; non-resident employment change`) | Rent | Published quarterly net change in non-resident employment from the configured MOM final Labour Market Report. | quarterly / quarterly final Labour Market Report | Quarterly non-resident employment change is a timely signal of changes in foreign labour demand that may affect rental demand. A timely foreign-labour demand signal that may precede or coincide with rental demand; the exact lag is not estimated. |
| **Private non-landed vacancy rate** (`SingStat M400841; Available and Vacant Non-Landed Properties`) | Rent | Derived share of available private non-landed residential units that are vacant. | quarterly / quarterly | Lower vacancy indicates tighter completed housing availability and may support rents. A contemporaneous tightness measure that may affect rents within the same quarter or with a short lag. |
| **URA non-landed rental index** (`data.gov.sg d_8e4c50283fb7052a391dfb746a05c853; property_type=Non-Landed; locality=Whole Island`) | Rent | URA rental index for registered tenancies of Singapore private non-landed residential properties, whole island. | quarterly / quarterly | Rental-market benchmark used to describe private non-landed rent movements. Benchmark outcome; demand and vacancy signals may lead or coincide with quarterly rental changes. |
| **Three-month Compounded SORA** (`SingStat M700071; Compounded Singapore Overnight Rate Average (SORA) - 3 Month`) | Sale | Three-month compounded Singapore Overnight Rate Average reported at month end. | monthly end of period / monthly | Higher short-term financing costs may weaken mortgage affordability and leveraged purchase demand. Financing conditions may affect affordability and purchase demand over subsequent quarters; the lag is not estimated. |
| **Real GDP growth** (`SingStat M015631; GDP In Chained (2015) Dollars`) | Sale | Official year-on-year real GDP growth for Singapore's overall economy in chained 2015 dollars. | quarterly / quarterly | Stronger real activity may support purchasing capacity and buyer confidence in the sale market. Broad activity may affect income expectations and purchasing capacity contemporaneously or over subsequent quarters; the lag is not estimated. |
| **URA non-landed price index** (`data.gov.sg d_97f8a2e995022d311c6c68cfda6d034c; property_type=Non-Landed`) | Sale | URA quality-adjusted price index for Singapore private non-landed residential properties. | quarterly / quarterly | Sale-market benchmark used to describe private non-landed price movements. Benchmark outcome; predictors may lead or coincide with quarterly price changes. |
| **Private non-landed pipeline supply** (`SingStat M400391; Total Non-Landed Properties group`) | Shared | Number of planned and under-construction private non-landed residential units in the official development pipeline. | quarterly / quarterly | A larger future supply pipeline may moderate sale prices and, after completion, rental pressure. Pipeline changes can lead market outcomes by several quarters or years because units affect usable supply only as projects complete. |


## Analysis

### Shared supply

The validated evidence shows that the private non-landed supply pipeline increased quarter on quarter; the private non-landed supply pipeline increased year on year. The associated mechanisms and lags are hypotheses from the indicator-selection framework, not causal estimates.

### Rental market

The validated evidence shows that the non-resident demand signal increased in the latest reported quarter; the non-resident demand signal increased year on year; the private non-landed vacancy rate increased quarter on quarter; the private non-landed vacancy rate decreased year on year; the private non-landed rental benchmark increased quarter on quarter; the private non-landed rental benchmark increased year on year. The associated mechanisms and lags are hypotheses from the indicator-selection framework, not causal estimates.

### Sale market

The validated evidence shows that official year-on-year real GDP growth decreased relative to the previous quarter; the SORA financing-rate proxy increased quarter on quarter using an incomplete quarter; the private non-landed sale-price benchmark decreased quarter on quarter; the private non-landed sale-price benchmark increased year on year. The associated mechanisms and lags are hypotheses from the indicator-selection framework, not causal estimates.

## Data processing and reliability

Official responses are preserved before parsing and tied to checksums. Exact series labels are selected, periods and units are normalized, the information cut-off is applied, and deterministic formulas produce changes and ratios. Validation checks required coverage, uniqueness, units, period formats, freshness, formula lineage, and zero denominators before any report is written.

Most data.gov.sg endpoints expose current-vintage histories rather than archived releases. Consequently, period cut-offs are enforced, but historical point-in-time availability remains unverified where an official release date or archived vintage is unavailable. The configured MOM final report is separately checked using its published release date.

## Validated evidence

### Shared

<!-- claim:claim-001 -->
- **Non-landed pipeline under-construction share**: 64.075 percent in 2026-Q2. Formula: `under_construction_non_landed / total_pipeline_non_landed * 100`; input period(s): 2026-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_residential_pipeline_supply](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view)
<!-- claim:claim-002 -->
- **Total Non-Landed Properties**: 51,677 dwelling units in 2026-Q2. Freshness: current; next observation not yet due. Source: [private_residential_pipeline_supply](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view)
<!-- claim:claim-003 -->
- **Total Non-Landed Properties (qoq_absolute_change)**: 3,566 dwelling units in 2026-Q2. Formula: `value - value_lag_1`; input period(s): 2026-Q1, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_residential_pipeline_supply](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view)
<!-- claim:claim-004 -->
- **Total Non-Landed Properties (yoy_pct)**: 6.608 percent in 2026-Q2. Formula: `(value / value_lag_4 - 1) * 100`; input period(s): 2025-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_residential_pipeline_supply](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view)

### Rent

<!-- claim:claim-005 -->
- **Non-Landed / Whole Island**: 162.500 index; 2009-Q1=100 in 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_rental_index](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view)
<!-- claim:claim-006 -->
- **Non-Landed / Whole Island (qoq_pct)**: 0.371 percent in 2026-Q2. Formula: `(value / value_lag_1 - 1) * 100`; input period(s): 2026-Q1, 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_rental_index](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view)
<!-- claim:claim-007 -->
- **Non-Landed / Whole Island (yoy_pct)**: 1.753 percent in 2026-Q2. Formula: `(value / value_lag_4 - 1) * 100`; input period(s): 2025-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_rental_index](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view)
<!-- claim:claim-008 -->
- **Non-Resident Population**: 1,906,660 persons in 2025. Freshness: current; next observation not yet due. Source: [non_resident_population](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view)
<!-- claim:claim-009 -->
- **Non-Resident Population (yoy_pct)**: 2.730 percent in 2025. Formula: `(value / value_lag_1 - 1) * 100`; input period(s): 2024, 2025. Freshness: current; next observation not yet due. Source: [non_resident_population](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view)
<!-- claim:claim-010 -->
- **Non-resident employment change**: 9,200 persons in 2026-Q2. Freshness: current; next observation not yet due. Source: [non_resident_employment_change](https://stats.mom.gov.sg/Pages/Labour-Market-Report-2Q-2026.aspx)
<!-- claim:claim-011 -->
- **Private non-landed vacancy rate**: 5.390 percent in 2026-Q2. Formula: `vacant_non_landed / available_non_landed * 100`; input period(s): 2026-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_non_landed_vacancy_rate](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view)
<!-- claim:claim-012 -->
- **Private non-landed vacancy rate (qoq_pp_change)**: 0.021 percentage points in 2026-Q2. Formula: `value - value_lag_1`; input period(s): 2026-Q1, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_non_landed_vacancy_rate](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view)
<!-- claim:claim-013 -->
- **Private non-landed vacancy rate (yoy_pp_change)**: -1.486 percentage points in 2026-Q2. Formula: `value - value_lag_4`; input period(s): 2025-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [private_non_landed_vacancy_rate](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view)

### Sale

<!-- claim:claim-014 -->
- **Compounded Singapore Overnight Rate Average (SORA) - 3 Month (quarter representation)**: 1.135 percent per annum in 2026-Q3. Source observation: 2026-07. Incomplete quarter. Formula: `last available month-end observation in quarter`; input period(s): 2026-07. Freshness: current; next observation not yet due. Source: [three_month_compounded_sora](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view)
<!-- claim:claim-015 -->
- **Compounded Singapore Overnight Rate Average (SORA) - 3 Month (quarter representation) (qoq_pp_change)**: 0.053 percentage points in 2026-Q3. Source observation: 2026-07. Incomplete quarter. Formula: `value - value_lag_1`; input period(s): 2026-Q2, 2026-Q3. Freshness: current; next observation not yet due. Source: [three_month_compounded_sora](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view)
<!-- claim:claim-016 -->
- **GDP In Chained (2015) Dollars**: 5.900 year-on-year percent change in 2026-Q2. Freshness: current; next observation not yet due. Source: [real_gdp_growth](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view)
<!-- claim:claim-017 -->
- **GDP In Chained (2015) Dollars (previous_quarter_pp_change)**: -0.400 percentage points in 2026-Q2. Formula: `value - value_lag_1`; input period(s): 2026-Q1, 2026-Q2. Freshness: current; next observation not yet due. Source: [real_gdp_growth](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view)
<!-- claim:claim-018 -->
- **Non-Landed**: 210.600 index; 2009-Q1=100 in 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_price_index](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view)
<!-- claim:claim-019 -->
- **Non-Landed (qoq_pct)**: -0.095 percent in 2026-Q2. Formula: `(value / value_lag_1 - 1) * 100`; input period(s): 2026-Q1, 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_price_index](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view)
<!-- claim:claim-020 -->
- **Non-Landed (yoy_pct)**: 1.838 percent in 2026-Q2. Formula: `(value / value_lag_4 - 1) * 100`; input period(s): 2025-Q2, 2026-Q2. Freshness: current; next observation not yet due. Source: [ura_non_landed_price_index](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view)

## Limitations

- Aggregate GDP is broader than household income, disposable income, or GDP per capita.
- Aggregate quality-adjusted index; not a transaction-price database.
- An incomplete quarter must be labelled.
- Annual end-June population stock.
- Based on registered tenancy agreements; not an asking-rent series.
- Derived from vacant and available units.
- Employment flow, not population stock.
- Excludes non-working non-residents.
- Executive Condominiums are excluded.
- Includes workers who may live outside private non-landed housing.
- Literature supports the broader non-resident demand mechanism rather than this exact quarterly series.
- Month-end financing proxy, not an individual mortgage rate.
- Must not be interpolated to quarterly frequency.
- Not all non-residents rent private non-landed homes.
- Not an advertised-listings measure.
- Pipeline units are not completed available stock.
- Project timing and status may be revised.
- Published GDP values may be revised.
- Quarterly representation uses the final available month-end observation.
- Current-vintage annual history; historical release vintages are not exposed by this endpoint.
- Current-vintage history; GDP observations may be revised after initial publication.
- Current-vintage history; historical release vintages are not exposed by this endpoint.
- Current-vintage history; project status and completion timing may be revised.
- Current-vintage history; the workflow labels a quarterly representation incomplete when the quarter-end month is unavailable.
- Release date is parsed from the configured final report; archive discovery is not automated.
