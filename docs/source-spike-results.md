# Official-Source Access Spike

## Result

The read-only spike confirmed that all nine required source series can be retrieved from official public endpoints. Eight structured series are available through data.gov.sg JSON endpoints. Quarterly non-resident employment change is available in the final Ministry of Manpower Labour Market Report and therefore needs a report parser rather than a stable time-series API.

| Source | Access result | Contract checked |
|---|---|---|
| URA non-landed price index | Pass | Dataset returns records matching `property_type = Non-Landed` |
| URA non-landed rental index | Pass | Dataset returns records matching `property_type = Non-Landed` and `locality = Whole Island` |
| Private residential pipeline supply | Pass | Official mirror contains non-landed series |
| Non-resident population | Pass | Exact `Non-Resident Population` series exists |
| Quarterly non-resident employment change | Pass | Final MOM report contains the expected quarterly non-resident employment text and an extractable value |
| Private non-landed vacancy inputs | Pass | Separate available and vacant non-landed series both exist |
| 3-month Compounded SORA | Pass | Exact 3-month compounded SORA series exists |
| Real GDP growth | Pass | Exact `GDP In Chained (2015) Dollars` series exists in YoY-growth table `M015631` |
| Real GDP quarter-on-quarter growth | Pass | Exact `GDP In Chained (2015) Dollars` series exists in seasonally adjusted QoQ table `M015922` |

## Reliability finding

Direct calls to the SingStat TableBuilder endpoints returned HTTP 502 during the spike, while the official data.gov.sg mirrors were available. The implementation therefore uses the mirrors as its machine-readable retrieval path and retains the SingStat pages as definition references. The unauthenticated data.gov.sg endpoint also returned HTTP 429 when more than five calls were made in quick succession. The production adapter must implement bounded retry/backoff, preserve the error in provenance when retries fail, and never silently present a previous snapshot as newly retrieved data.

The successful targeted verification is recorded in `data/raw/spike_20261001T084622Z/manifest.json`. Earlier spike manifests are retained as evidence of the failed direct-endpoint and rate-limit tests.

## Production retrieval follow-up

An early production-layer integration check downloaded the URA price-index response but received HTTP 403 from the MOM report page. The retrieval layer correctly classified that response as non-retryable and did not substitute another value. A subsequent rate-limited live run retrieved the original eight configured sources with HTTP 200; the official GDP QoQ source was then added and independently verified against SingStat table M015922. The contrast is retained because public-page access can be intermittent: future live failures must still halt or use an explicitly approved, visibly labelled cached fallback.
