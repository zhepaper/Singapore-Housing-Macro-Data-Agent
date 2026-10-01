# Literature Review and Indicator Selection

## 1. Research Scope

Singapore's residential market comprises institutionally distinct public and private segments. This study focuses on the **URA private non-landed residential segment**, which consists primarily of condominiums and private apartments, and considers both sale-price and rental conditions.

- HDB flats are excluded because their eligibility, ownership, resale, and rental rules differ materially from those of private housing.
- Landed properties are excluded because they form a distinct and less accessible market, particularly for foreign purchasers.
- Where Executive Condominiums are incorporated within an official URA series, their treatment follows the published statistical definition and is recorded in the dataset metadata.
- The URA Non-Landed Property Price Index and Rental Index are retained as observed market benchmarks; they are not treated as predictors or reconstructed from property-level transactions.
- The workflow focuses on five publicly accessible macroeconomic, financial, demographic, and market-level predictors.

The predictor set is organised as follows:

- Shared supply factor: **Private residential pipeline supply**
- Rent-specific factors: **Non-resident rental demand** and **Private residential vacancy rate**
- Sale-specific factors: **3-month Compounded SORA** and **Real GDP growth**

## 2. Shared Supply Factor

### **Private Residential Pipeline Supply**

Pipeline supply is retained as the only factor shared by the sale and rental analyses, although its transmission differs across the two markets. [Tu (2004)](https://journals.sagepub.com/doi/10.1080/0042098042000178708) finds that total housing stock has a significant long-run relationship with Singapore private housing prices, while the [IMF (2018)](https://www.imf.org/-/media/files/publications/cr/2018/cr18245.pdf) reports that greater private residential supply is generally associated with lower long-run prices. These studies examine existing stock or available units rather than URA's pipeline series. Pipeline supply is therefore used as a forward-looking operational measure of the broader supply mechanism identified in the literature.

- **Sale mechanism:** A larger future supply may reduce expected scarcity and increase anticipated competition across developments, affecting current purchase decisions before construction is completed.
- **Rent mechanism:** Pipeline units must first be completed, become occupiable, and enter the rental stock before they can affect vacancy and rents. The rental effect is therefore lagged.
- **Interpretation constraint:** Pipeline units are not treated as currently available housing. Expected completion dates and unit counts may be revised because of project changes or delays.

## 3. Rent-Specific Factors

Rental conditions are analysed through tenant demand and the current availability of completed housing.

### **Non-Resident Rental Demand**

Non-resident rental demand is selected as a rent-specific factor because foreigners living and working in Singapore are more likely than citizens and permanent residents to depend on rental accommodation. [Chia, Li and Tang (2017)](https://ideas.repec.org/a/eee/jhouse/v36y2017icp44-61.html) identify demographics as an important fundamental in Singapore's private housing market, while [Ji and Bhandari (2022)](https://ideas.repec.org/a/eme/ijhmap/ijhma-02-2021-0023.html) discuss the importance of non-residents to Singapore's rental market. The factor is represented by two distinct but complementary official measures.

- **Structural measure — Annual non-resident population growth:** The annual population series measures changes in the overall number of non-residents living in Singapore and therefore captures the size of the broader foreign-facing rental-demand base.
- **Timely signal — Quarterly non-resident employment change:** The quarterly series measures the quarter-on-quarter change in employed non-residents. It provides a more recent indication of the direction of foreign labour demand between annual population observations.
- **Measurement distinction:** Quarterly non-resident employment change is employment data, not population data. It excludes non-working groups such as students and dependants and may include workers living in dormitories, employer-provided accommodation, HDB flats, or other housing outside the private non-landed market. It must not be interpreted as quarterly non-resident population growth.
- **Evidence constraint:** The literature supports the underlying relationship between non-resident presence and rental demand but does not directly test quarterly non-resident employment change as a predictor of private rents. The employment series is therefore a timely operational signal rather than a literature-validated standalone predictor.
- **Reporting treatment:** The annual population series and quarterly employment series are retained at their native frequencies and reported separately. The workflow neither interpolates annual population nor combines the two measures into a synthetic indicator.

### **Private Residential Vacancy Rate**

The vacancy rate is selected to measure current rental-market tightness. Within the space-market framework of [DiPasquale and Wheaton (1992)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6229.00579), rents reflect the balance between demand for occupation and the completed stock available for use. A lower vacancy rate is consistent with stronger absorption and fewer alternatives for tenants, while a higher rate indicates greater spare capacity.

- **Rent mechanism:** Lower vacancy indicates a tighter completed-housing market and potentially stronger landlord bargaining conditions; higher vacancy indicates more available capacity and greater competition among landlords.
- **Singapore evidence:** [URA and HDB (2026)](https://www.ura.gov.sg/news/media/pr26-03/) report that increased housing completions helped alleviate rental-market tightness and moderate rent increases.
- **Interpretation constraint:** Direct Singapore-specific academic estimates of the vacancy-rent relationship are limited. Vacancy is therefore treated as a contemporaneous market-tightness indicator, not as a proven standalone leading predictor.
- **Measurement constraint:** URA infers private residential vacancy from water and electricity consumption rather than advertised rental listings.

## 4. Sale-Specific Factors

Sale prices are analysed through financing conditions and aggregate purchasing capacity.

### **3-Month Compounded SORA**

The 3-month Compounded SORA is selected as the financing indicator because higher borrowing costs can reduce mortgage affordability and leveraged investment demand. [Tu (2004)](https://journals.sagepub.com/doi/10.1080/0042098042000178708) finds that housing user cost contributes to short-run private price dynamics, while the [IMF (2018)](https://www.imf.org/-/media/files/publications/cr/2018/cr18245.pdf) reports a generally negative long-run relationship between real interest rates and private residential prices. [Rangel and Ng (2017)](https://www.mfa.com.my/wp-content/uploads/2017/12/vol252_pp.15-31-Rangel-Ng.pdf) find that the real prime lending rate is not consistently significant across market regimes.

- **Sale mechanism:** Tighter financing conditions raise the cost of mortgage-funded purchases and may weaken owner-occupier purchasing capacity and leveraged investment demand.
- **Operational choice:** The earlier studies use user cost, real interest rates, or prime lending rates rather than SORA. The workflow uses the monthly end-of-period 3-month Compounded SORA series in SingStat table `M700071`, whose original source is the Monetary Authority of Singapore, as a contemporary and publicly accessible proxy for short-term Singapore-dollar financing conditions. The final available month-end observation in each quarter is used for quarterly comparison.
- **Interpretation constraint:** SORA is neither an individual borrower's mortgage rate nor a deterministic predictor of sale-price changes. It is not used as a primary rental predictor.

### **Real GDP Growth**

Real GDP growth is selected as the sale-side macroeconomic indicator because economic expansion may strengthen income expectations, employment security, and buyer confidence. [Tu (2004)](https://journals.sagepub.com/doi/10.1080/0042098042000178708) identifies a significant long-run relationship between real GDP per capita and private housing prices. The [IMF (2018)](https://www.imf.org/-/media/files/publications/cr/2018/cr18245.pdf) and [Rangel and Ng (2017)](https://www.mfa.com.my/wp-content/uploads/2017/12/vol252_pp.15-31-Rangel-Ng.pdf) similarly examine GDP per capita or real disposable income in relation to private residential prices.

- **Sale mechanism:** Stronger economic activity may support household purchasing capacity, confidence, and demand for private housing.
- **Operational choice:** Quarterly real GDP growth provides a timely and reproducible measure of aggregate economic conditions, although it is broader than household disposable income or GDP per capita.
- **Interpretation constraint:** The reviewed Singapore literature does not directly estimate GDP as a determinant of private residential rents. GDP is therefore retained as a sale-specific predictor rather than assigned to both markets.

## 5. Selection Summary

| Classification | Predictor | Primary mechanism |
|---|---|---|
| Shared | **Private residential pipeline supply** | Expected future supply for Sale; completed supply with a lag for Rent |
| Rent-specific | **Non-resident rental demand** | Foreign-facing tenant demand, measured by annual population growth and supplemented by quarterly employment change |
| Rent-specific | **Private residential vacancy rate** | Current rental-market tightness |
| Sale-specific | **3-month Compounded SORA** | Financing conditions and mortgage affordability |
| Sale-specific | **Real GDP growth** | Purchasing capacity and buyer confidence |

## References

- Chia, W.-M., Li, M. and Tang, Y. (2017). [Public and private housing markets dynamics in Singapore: The role of fundamentals](https://ideas.repec.org/a/eee/jhouse/v36y2017icp44-61.html). *Journal of Housing Economics*, 36, 44-61.
- DiPasquale, D. and Wheaton, W. C. (1992). [The Markets for Real Estate Assets and Space: A Conceptual Framework](https://onlinelibrary.wiley.com/doi/abs/10.1111/1540-6229.00579). *Real Estate Economics*, 20(2), 181-198.
- International Monetary Fund. (2018). [Singapore: 2018 Article IV Consultation—Staff Report](https://www.imf.org/-/media/files/publications/cr/2018/cr18245.pdf), Appendix VII.
- Ji, P. I. and Bhandari, S. B. (2022). [The price-rent dynamics and linkage of urban housing: evidence from Singapore](https://ideas.repec.org/a/eme/ijhmap/ijhma-02-2021-0023.html). *International Journal of Housing Markets and Analysis*, 15(3), 504-520.
- Rangel, G. J. and Ng, J. W. J. (2017). [Macroeconomic Drivers of Singapore Private Residential Prices: A Markov-Switching Approach](https://www.mfa.com.my/wp-content/uploads/2017/12/vol252_pp.15-31-Rangel-Ng.pdf). *Capital Markets Review*, 25(2), 15-31.
- Tu, Y. (2004). [The Dynamics of the Singapore Private Housing Market](https://journals.sagepub.com/doi/10.1080/0042098042000178708). *Urban Studies*, 41(3), 605-619.
- Urban Redevelopment Authority. [Coverage and Methodology](https://eservice.ura.gov.sg/reis/coverageandMethodology).
- Urban Redevelopment Authority and Housing & Development Board. (2026). [Extension of temporary relaxation of occupancy cap for rental of HDB flats and private residential properties until 31 December 2028](https://www.ura.gov.sg/news/media/pr26-03/).
