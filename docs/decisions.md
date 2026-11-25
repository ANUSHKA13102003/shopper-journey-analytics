# Engineering and Analytical Decisions

1. **DuckDB out-of-core processing**: REES46 Oct+Nov totals 14.68 GB uncompressed (109.95M rows) and Criteo Uplift is 13.98M rows. Using DuckDB with `memory_limit = '4GB'` and `temp_directory = 'data/interim/duckdb_tmp'` keeps peak RAM low and avoids loading raw CSVs into pandas.
2. **Criteo Uplift download source**: `scikit-uplift`'s `fetch_criteo` URL returned HTTP 404 and the direct `go.criteo.net` stream stalled; switched to the official Hugging Face mirror (`criteo/criteo-uplift`, `criteo-research-uplift-v2.1.csv.gz`) via `curl`.
3. **Python version in `render.yaml`**: Pinned `PYTHON_VERSION` to `3.12.8` because `numpy==2.5.5` and `scipy==1.18.1` require Python `>=3.12`.
4. **Session funnel denominator**: Restricted `sql/01_funnel.sql` to sessions with at least one `view` event (`has_view = 1`), and attributed each session to its entry `category_code` and first positive `price` band so stages are strictly monotonic (`viewed >= carted >= purchased`).
5. **Existing-user washout in cohorts**: Excluded users first seen in the first 7 days (`2019-10-01` to `2019-10-07`) from cohort retention so returning pre-existing shoppers do not inflate new-user retention.
6. **Strict full-window eligibility**: Only users whose `first_seen_date <= max_date - N` are included in `D7`, `D14`, `D28`, and `D1..D28` retention denominators.
7. **Intention-to-Treat (ITT) for Part B**: Evaluated `treatment = 1` vs `treatment = 0` rather than `exposure = 1` vs `0` to preserve randomization, while reporting the `3.60%` treatment exposure rate as a delivery diagnostic.
8. **Collapsing tied quartiles in Criteo segments**: Several anonymized features (`f1, f4, f5, f7, f9, f10, f11`) are concentrated at a mode where `q25 == q50` or `q25 == q50 == q75`. We collapsed identical cutpoints into non-overlapping bins (`25` total cuts) and applied Benjamini-Hochberg FDR correction across all `25` tests.

