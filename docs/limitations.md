# Known Limitations and Future Extensions

## Current limitations

- **No trained forecast model.** The report identifies and describes candidate predictors. It does not estimate predictive accuracy, causal effects, or future price/rent changes.
- **Aggregate market scope.** Results apply to Singapore private non-landed residential property as a broad segment. They do not represent every condominium project, district, unit type, or tenant/owner group.
- **Current-vintage retrieval.** Several official endpoints expose the latest revised history without archived release vintages. Period and report-release cut-offs are enforced where observable, but historical backtests would need archived vintages to eliminate look-ahead from revisions.
- **MOM HTML dependency.** Quarterly non-resident employment change is extracted from a public final-report page because no stable official series endpoint with the required resident split was found. Wording changes intentionally fail closed and require review.
- **Proxy interpretation.** Non-resident employment change is a quarterly labour-demand flow, not population. The literature directly supports the broader non-resident housing-demand mechanism, not this exact series as a proven rental predictor.
- **Timing mismatch.** Annual population, quarterly market series, and monthly SORA update at different speeds. The workflow preserves native frequency instead of inventing aligned observations.
- **Aggregate availability.** Pipeline supply is not completed stock, and vacancy is an aggregate physical-market measure. Project completion timing, revisions, and location mix may weaken their relationship with the selected benchmarks.
- **Public endpoint reliability.** Rate limits, transient outages, and access controls can interrupt live retrieval. Retries are bounded; cached fallback is explicit and changes status to `partial`.

## Sensible extensions

1. Archive scheduled official releases to construct reproducible historical vintages.
2. Add release-calendar metadata and provisional/revised flags where providers expose them.
3. Evaluate lag structures and out-of-sample predictive value with a separate modelling layer.
4. Add market segmentation only where comparable public benchmarks and predictors exist.
5. Replace MOM HTML parsing if an official structured resident-status employment series becomes available.
6. Add CI for the offline suite and a low-frequency, opt-in live source health check.
