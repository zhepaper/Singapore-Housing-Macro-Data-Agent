# Singapore Private Residential Market Predictor Report

**Information cut-off:** 2026-10-01

## Scope and Method

Singapore private non-landed residential sale prices and rents, using public macroeconomic, financial, demographic, and market-level indicators.

Describe recent validated movements in the selected indicators and explain how they may be informative for sale-price and rental-market monitoring.

This report is generated only from the Stage 3 validated evidence bundle. All numerical claims below are rendered by deterministic code; the qualitative interpretation does not perform new calculations. This is an indicator-monitoring report, not a forecasting model or a causal estimate.

## Analytical Interpretation

### Executive Summary

The validated indicators provide a descriptive view of market conditions. They should be read as potentially informative signals rather than a causal model or forecast.

### Sale-Market Interpretation

The validated change signals are mixed and do not support a single directional conclusion. These descriptive movements should not be interpreted as causal estimates or forecasts.

### Rental-Market Interpretation

The validated change signals are mixed and do not support a single directional conclusion. These descriptive movements should not be interpreted as causal estimates or forecasts.

### Shared Signals

The validated change signals are positive, although their mechanisms and timing may differ. These descriptive movements should not be interpreted as causal estimates or forecasts.

### Cross-Series Interpretation

Signals across financing, demand, supply, and market outcomes may move at different times. Agreement can strengthen a descriptive reading, while disagreement should remain visible rather than being forced into one conclusion.

### Conclusion

The evidence supports continued monitoring, with conclusions bounded by source timing, frequency, and data quality.

## Indicator Rationale and Literature

| Indicator | Market | Selection rationale | Literature support |
|---|---|---|---|
| Non-resident employment change | Rent | Quarterly non-resident employment change is a timely demand signal, but it is an employment flow rather than a population stock. | `JiBhandari2022` |
| Non-resident population | Rent | The non-resident population is a structural measure of part of the potential foreign-facing tenant base. | `ChiaLiTang2017`, `JiBhandari2022` |
| Private non-landed vacancy rate | Rent | Vacancy measures completed-market tightness and may be informative for rental pressure. | `DiPasqualeWheaton1992`, `URAHDB2026` |
| URA private non-landed rental index | Rent | The official URA non-landed whole-island rental index is the rental-market outcome benchmark; it is reported as an outcome and is not used as a predictor. | Not supplied |
| Real GDP growth | Sale | Broad economic activity may affect income expectations, purchasing capacity, and buyer confidence. | `Tu2004`, `IMF2018`, `RangelNg2017` |
| Three-month Compounded SORA | Sale | Short-term financing conditions may affect mortgage affordability and leveraged purchase demand in the sale market. | `Tu2004`, `IMF2018`, `RangelNg2017` |
| URA private non-landed price index | Sale | The official URA non-landed price index is the sale-market outcome benchmark; it is reported as an outcome and is not used as a predictor. | Not supplied |
| Private non-landed residential pipeline | Shared | The future housing pipeline may affect sale and rental conditions after projects are completed. | `Tu2004`, `IMF2018` |

## Validated Evidence

### Sale Market

<!-- claim:CLAIM-010 -->
- **Real GDP growth**: 5.9 year-on-year percent change in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Source: [Quarterly real GDP growth (M015631)](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view) (`real_gdp_growth`).

<!-- claim:CLAIM-011 -->
- **Real GDP growth (qoq_percentage_point_change)**: -0.4 percentage points in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_point_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [Quarterly real GDP growth (M015631)](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view) (`real_gdp_growth`).

<!-- claim:CLAIM-012 -->
- **Three-month Compounded SORA**: 1.083 percent per annum in 2026-06. Frequency: monthly; update frequency: monthly. Source: [Singapore dollar interest rate benchmarks (M700071)](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view) (`three_month_compounded_sora`).

<!-- claim:CLAIM-013 -->
- **Three-month Compounded SORA (quarterly last)**: 1.083 percent per annum in 2026-Q2. Frequency: quarterly; update frequency: monthly. Derivation: `monthly to quarterly last; policy=reject`; input period(s): 2026-04, 2026-05, 2026-06. Source: [Singapore dollar interest rate benchmarks (M700071)](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view) (`three_month_compounded_sora`).

<!-- claim:CLAIM-014 -->
- **Three-month Compounded SORA (quarterly last) (qoq_basis_point_change)**: 1.17 basis points in 2026-Q2. Frequency: quarterly; update frequency: monthly. Derivation: `basis_point_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [Singapore dollar interest rate benchmarks (M700071)](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view) (`three_month_compounded_sora`).

<!-- claim:CLAIM-015 -->
- **URA private non-landed price index**: 210.6 index; 2009-Q1=100 in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Source: [URA private residential property price index by type](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view) (`ura_non_landed_price_index`).

<!-- claim:CLAIM-016 -->
- **URA private non-landed price index (qoq_percentage_change)**: -0.095 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [URA private residential property price index by type](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view) (`ura_non_landed_price_index`).

<!-- claim:CLAIM-017 -->
- **URA private non-landed price index (yoy_percentage_change)**: 1.838 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_change using calendar lag 4`; input period(s): 2025-Q2, 2026-Q2. Source: [URA private residential property price index by type](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view) (`ura_non_landed_price_index`).

### Rental Market

<!-- claim:CLAIM-001 -->
- **Non-resident employment change**: 9,200 persons in 2026-Q2. Frequency: quarterly; update frequency: quarterly final Labour Market Report. Source: [Labour Market Report 2Q 2026](https://stats.mom.gov.sg/Pages/Labour-Market-Report-2Q-2026.aspx) (`non_resident_employment_change`).

<!-- claim:CLAIM-002 -->
- **Non-resident population**: 1,906,660 persons in 2025. Frequency: annual; update frequency: annual. Source: [Singapore population by residential status](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view) (`non_resident_population`).

<!-- claim:CLAIM-003 -->
- **Non-resident population (yoy_percentage_change)**: 2.73 percent in 2025. Frequency: annual; update frequency: annual. Derivation: `percentage_change using calendar lag 1`; input period(s): 2024, 2025. Source: [Singapore population by residential status](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view) (`non_resident_population`).

<!-- claim:CLAIM-004 -->
- **Private non-landed vacancy rate**: 5.39 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Source: [Available and vacant private residential properties (M400841)](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view) (`private_non_landed_vacancy_rate`).

<!-- claim:CLAIM-005 -->
- **Private non-landed vacancy rate (qoq_percentage_point_change)**: 0.021 percentage points in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_point_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [Available and vacant private residential properties (M400841)](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view) (`private_non_landed_vacancy_rate`).

<!-- claim:CLAIM-006 -->
- **Private non-landed vacancy rate (yoy_percentage_point_change)**: -1.486 percentage points in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_point_change using calendar lag 4`; input period(s): 2025-Q2, 2026-Q2. Source: [Available and vacant private residential properties (M400841)](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view) (`private_non_landed_vacancy_rate`).

<!-- claim:CLAIM-007 -->
- **URA private non-landed rental index**: 162.5 index; 2009-Q1=100 in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Source: [URA private residential rental index by type and locality](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view) (`ura_non_landed_rental_index`).

<!-- claim:CLAIM-008 -->
- **URA private non-landed rental index (qoq_percentage_change)**: 0.371 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [URA private residential rental index by type and locality](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view) (`ura_non_landed_rental_index`).

<!-- claim:CLAIM-009 -->
- **URA private non-landed rental index (yoy_percentage_change)**: 1.753 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_change using calendar lag 4`; input period(s): 2025-Q2, 2026-Q2. Source: [URA private residential rental index by type and locality](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view) (`ura_non_landed_rental_index`).

### Shared Indicators

<!-- claim:CLAIM-018 -->
- **Private non-landed residential pipeline**: 51,677 dwelling units in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Source: [Private residential units in the pipeline (M400391)](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) (`private_residential_pipeline_supply`).

<!-- claim:CLAIM-019 -->
- **Private non-landed residential pipeline (qoq_absolute_change)**: 3,566 dwelling units in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `absolute_change using calendar lag 1`; input period(s): 2026-Q1, 2026-Q2. Source: [Private residential units in the pipeline (M400391)](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) (`private_residential_pipeline_supply`).

<!-- claim:CLAIM-020 -->
- **Private non-landed residential pipeline (yoy_percentage_change)**: 6.608 percent in 2026-Q2. Frequency: quarterly; update frequency: quarterly. Derivation: `percentage_change using calendar lag 4`; input period(s): 2025-Q2, 2026-Q2. Source: [Private residential units in the pipeline (M400391)](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) (`private_residential_pipeline_supply`).

## Data Quality and Limitations

- Information is limited to data available by 2026-10-01.
- The report is descriptive and does not estimate causal effects or produce a formal forecast.
- Displayed values are rounded to at most three decimal places; exact decimal values remain in the claim ledger.
- POTENTIAL_LOOK_AHEAD: Predictor was not available by the end of its aligned outcome quarter; the contemporaneous alignment is descriptive and must not be treated as a real-time forecasting feature.
- Derived deterministically from the recorded source periods.
- No observation-level release date was supplied; the workflow relies on the approved availability rule.

## Sources

- `ura_non_landed_price_index`: [URA private residential property price index by type](https://data.gov.sg/datasets/d_97f8a2e995022d311c6c68cfda6d034c/view) — Urban Redevelopment Authority via data.gov.sg
- `ura_non_landed_rental_index`: [URA private residential rental index by type and locality](https://data.gov.sg/datasets/d_8e4c50283fb7052a391dfb746a05c853/view) — Urban Redevelopment Authority via data.gov.sg
- `private_residential_pipeline_supply`: [Private residential units in the pipeline (M400391)](https://data.gov.sg/datasets/d_055b6549444dedb341c50805d9682a41/view) — Urban Redevelopment Authority via SingStat and data.gov.sg
- `non_resident_population`: [Singapore population by residential status](https://data.gov.sg/datasets/d_3d227e5d9fdec73f3bcadce671c333a6/view) — Singapore Department of Statistics via data.gov.sg
- `non_resident_employment_change`: [Labour Market Report 2Q 2026](https://stats.mom.gov.sg/Pages/Labour-Market-Report-2Q-2026.aspx) — Ministry of Manpower
- `private_non_landed_vacancy_rate`: [Available and vacant private residential properties (M400841)](https://data.gov.sg/datasets/d_01e3556fb916ca19a7e29fc39520fa78/view) — Urban Redevelopment Authority via SingStat and data.gov.sg
- `three_month_compounded_sora`: [Singapore dollar interest rate benchmarks (M700071)](https://data.gov.sg/datasets/d_5fe5a4bb4a1ecc4d8a56a095832e2b24/view) — Monetary Authority of Singapore via SingStat and data.gov.sg
- `real_gdp_growth`: [Quarterly real GDP growth (M015631)](https://data.gov.sg/datasets/d_a5ff719648a0e6d4b4c623ee383ab686/view) — Singapore Department of Statistics via data.gov.sg

### Literature Used for Predictor Rationale

- `ChiaLiTang2017`: [Chia, W.-M., Li, M. and Tang, Y. (2017). Public and private housing markets dynamics in Singapore: The role of fundamentals. Journal of Housing Economics, 36, 44-61.](https://ideas.repec.org/a/eee/jhouse/v36y2017icp44-61.html)
- `DiPasqualeWheaton1992`: [DiPasquale, D. and Wheaton, W. C. (1992). The Markets for Real Estate Assets and Space: A Conceptual Framework. Real Estate Economics, 20(2), 181-198.](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6229.00579)
- `IMF2018`: [International Monetary Fund (2018). Singapore: 2018 Article IV Consultation—Staff Report, Appendix VII.](https://www.imf.org/-/media/files/publications/cr/2018/cr18245.pdf)
- `JiBhandari2022`: [Ji, P. I. and Bhandari, S. B. (2022). The price-rent dynamics and linkage of urban housing: evidence from Singapore. International Journal of Housing Markets and Analysis, 15(3), 504-520.](https://ideas.repec.org/a/eme/ijhmap/ijhma-02-2021-0023.html)
- `RangelNg2017`: [Rangel, G. J. and Ng, J. W. J. (2017). Macroeconomic Drivers of Singapore Private Residential Prices: A Markov-Switching Approach. Capital Markets Review, 25(2), 15-31.](https://www.mfa.com.my/wp-content/uploads/2017/12/vol252_pp.15-31-Rangel-Ng.pdf)
- `Tu2004`: [Tu, Y. (2004). The Dynamics of the Singapore Private Housing Market. Urban Studies, 41(3), 605-619.](https://journals.sagepub.com/doi/10.1080/0042098042000178708)
- `URAHDB2026`: [Urban Redevelopment Authority and Housing & Development Board (2026). Extension of temporary relaxation of occupancy cap for rental of HDB flats and private residential properties until 31 December 2028.](https://www.ura.gov.sg/news/media/pr26-03/)
