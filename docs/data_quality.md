# Data Quality Report

## Part A: REES46 eCommerce Behavior Data (Oct-Nov 2019)

Profiled directly from `data/raw/rees46/2019-Oct.csv` (5.67 GB) and `2019-Nov.csv` (9.01 GB) using DuckDB (`outputs/data_quality.json`):

| Check | Value | Notes / Action Taken |
| --- | ---: | --- |
| Total rows | 109,950,743 | Combined Oct 2019 and Nov 2019 logs |
| Date range (UTC) | `2019-10-01 00:00:00` to `2019-11-30 23:59:59` | Full 61-day window |
| Distinct users | 5,316,649 | `user_id` has `0` nulls |
| Distinct sessions | 23,016,650 | `user_session` has `12` nulls (excluded from session funnel) |
| `view` events | 104,335,509 | 94.89% of all events |
| `cart` events | 3,955,446 | 3.60% of all events |
| `purchase` events | 1,659,788 | 1.51% of all events |
| `remove_from_cart` events | 0 | Column value absent in Oct-Nov 2019 files |
| Null `category_code` | 35,413,780 | 32.21% of rows; mapped to `'unknown'` in `sql/01_funnel.sql` |
| Null `brand` | 15,331,243 | 13.94% of rows; not used in funnel/cohort grouping |
| `price <= 0` or null | 256,761 | 0.23% of rows; bucketed as `'invalid_or_free'` and excluded from revenue sums |
| Exact key duplicates | 130,750 | 0.12% of rows sharing `(event_time, event_type, product_id, user_id, user_session)`; session funnel uses `MAX(CASE ...)` flags so duplicate events do not double-count session conversion |

### Oddities & Decisions
- **Missing `remove_from_cart`**: Although the Kaggle schema description mentions `remove_from_cart`, the Oct-Nov 2019 multi-category store files contain only `view`, `cart`, and `purchase`.
- **Null `user_session` (12 rows)**: Excluded in `WHERE user_session IS NOT NULL AND user_id IS NOT NULL`.
- **Direct purchase without view**: Some sessions record a `cart` or `purchase` without a `view` in the same session; `sql/01_funnel.sql` restricts the session funnel to sessions with `has_view = 1` so all three stages share a consistent denominator.

## Part B: Criteo Uplift Prediction Dataset v2.1

Profiled directly from `data/raw/criteo-research-uplift-v2.1.csv.gz` (296.9 MB compressed) using DuckDB (`outputs/criteo_summary.json`):

| Check | Value | Notes / Action Taken |
| --- | ---: | --- |
| Total rows | 13,979,592 | Each row represents one user in the randomized trial |
| Treatment / Control split | 85.00% / 15.00% | `11,882,655` treated vs `2,096,937` control (deliberately uneven) |
| Exposure rate | 3.60% treat / 0.00% ctrl | Zero contamination in control; ITT analysis used on `treatment` |
| Max `\|SMD\|` (`f0..f11`) | 0.0488 | All 12 covariates well below `0.10` balance threshold |
| Zero-inflated / tied features | 7 of 12 features | `f1, f4, f5, f7, f9, f10, f11` have tied quartiles; collapsed to non-overlapping quantile bins (`25` cuts total) |
