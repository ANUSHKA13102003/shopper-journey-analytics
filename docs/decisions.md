# Engineering and Analytical Decisions

1. **DuckDB out-of-core processing**: REES46 Oct+Nov totals 14.68 GB uncompressed (`109,950,743` rows) and Criteo Uplift has `13,979,592` rows. Streaming CSVs directly in DuckDB (`memory_limit = '4GB'`, `temp_directory = 'data/interim/duckdb_tmp'`) keeps peak memory low and exports `<100 KB` of Parquet/JSON files to `outputs/`.
2. **Criteo Uplift download mirror**: `scikit-uplift`'s `fetch_criteo` S3 bucket returned HTTP 404 and `go.criteo.net` stalled; switched to the official Hugging Face mirror (`criteo/criteo-uplift`, `criteo-research-uplift-v2.1.csv.gz`).
3. **Python 3.12.8 on Render**: Pinned `PYTHON_VERSION=3.12.8` on Render because `numpy==2.5.5` and `scipy==1.18.1` require Python `>=3.12`.
4. **Cold-start reduction and keep-alive**:
   - The Streamlit app loads only pre-aggregated Parquet/JSON files (`<100 KB`) inside a single `@st.cache_data(ttl=3600)` call and imports zero heavy training/CLI packages at runtime.
   - Configured Render's health check to Streamlit's lightweight `/_stcore/health` endpoint (`render.yaml` and Render service `srv-dc3hopijnfac73apequ0`).
   - Added a scheduled GitHub Actions workflow (`.github/workflows/keepalive.yml`) that pings `https://shopper-journey-analytics.onrender.com/_stcore/health` every 5 minutes (`*/5 * * * *`) to reduce free-tier spin-down delays, paired with an always-on static HTML report on GitHub Pages (`docs/index.html`).
5. **Monotonic session funnel**: Restricted `sql/01_funnel.sql` to sessions with `has_view = 1` (`23,005,603` sessions) and attributed each session to its entry `category_code` and first positive `price` band so stages never increase (`viewed >= carted >= purchased`).
6. **7-day washout and full-window cohorts**: Excluded users first seen between `2019-10-01` and `2019-10-07` as pre-existing shoppers, and enforced `first_seen_date <= max_date - N` so right-censored cohorts cannot depress `D7`, `D14`, or `D28` return rates.
7. **Intention-to-Treat (ITT) and tied-quartile handling**: Analyzed `treatment = 1` vs `0` rather than post-assignment `exposure` (`3.60%`) to avoid selection bias. Collapsed mode-tied quartiles on 7 zero-inflated Criteo features into `25` non-overlapping cuts and applied Benjamini-Hochberg FDR correction (`alpha = 0.05`).
