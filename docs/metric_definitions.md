# Metric Definitions

## Part A: Shopper Journey & Retention (REES46)

### Session Funnel (`sql/01_funnel.sql`)
- **Eligible Session**: A `user_session` with non-null `user_id` and `user_session` that contains at least one `view` event (`has_view = 1`).
- **Stage 1 — View (`sessions_viewed`)**: Count of eligible sessions.
- **Stage 2 — Cart (`sessions_carted`)**: Eligible sessions with at least one `cart` event.
- **Stage 3 — Purchase (`sessions_purchased`)**: Eligible sessions with both a `cart` event and a `purchase` event.
- **View-to-Cart Rate**: `sessions_carted / sessions_viewed`.
- **Cart-to-Purchase Rate**: `sessions_purchased / sessions_carted`.
- **View-to-Purchase Rate**: `sessions_purchased / sessions_viewed`.
- **Cart Abandonment Rate**: `sessions_cart_abandoned / sessions_carted`, where `cart_abandoned = 1` if `has_cart = 1` and `has_purchase = 0`.
- **Time from First View to Purchase**: `DATE_DIFF('second', first_view_time, first_purchase_time) / 60.0` in minutes, for sessions where `first_purchase_time >= first_view_time`. Summarized with median, 25th percentile (`p25`), and 75th percentile (`p75`).
- **Top-Level Category**: First segment of `category_code` before `.` (`'unknown'` when null), taken at the session's earliest event (`entry_category`).
- **Price Band**: First positive `price` in the session, bucketed into `under_25`, `25_to_99`, `100_to_299`, `300_plus`, or `invalid_or_free` if no positive price exists.

### Cohorts & Retention (`sql/02_cohorts.sql`, `sql/03_retention_curve_and_repeat.sql`)
- **New-User Approximation**: Because first-seen in a 2-month log is not the same as a brand-new account, users whose `first_seen_date` falls in the first 7 days of the dataset (`min_date .. min_date + 6 days`) are treated as pre-existing users and excluded from cohort metrics.
- **Cohort Week**: Monday-aligned `DATE_TRUNC('week', first_seen_date)` for eligible users.
- **D7 / D14 / D28 Return Rate (Cumulative Window)**: Share of eligible users who return on at least one day in `[first_seen_date + 1, first_seen_date + N]`. Computed strictly for users whose full `N`-day window lies inside the dataset (`first_seen_date <= max_date - N`).
- **Exact-Day Retention Curve (`D1..D28`)**: Share of eligible users active specifically on `first_seen_date + d` for `d = 1..28`, restricted to users with `first_seen_date <= max_date - d`.
- **28-Day Repeat-Purchase Rate**: Among buyers whose first `purchase` occurred on or after `min_date + 7` and at least 28 days before `max_date`, the share who make another purchase on a later date within `[first_purchase_date + 1, first_purchase_date + 28]`.

## Part B: Ad Uplift Experiment (Criteo Uplift v2.1)
- **Intention-to-Treat (ITT)**: All primary comparisons compare `treatment = 1` vs `treatment = 0` regardless of `exposure` (`3.60%` in treatment, `0.00%` in control) to preserve randomization.
- **Standardized Mean Difference (SMD)**: `(mean_treat - mean_ctrl) / sqrt((var_treat + var_ctrl) / 2)`.
- **Absolute Lift per 1,000 Users**: `(p_treat - p_ctrl) * 1000`, with unpooled Wald 95% confidence interval.
- **Relative Lift**: `(p_treat - p_ctrl) / p_ctrl`, with asymptotic log-relative-risk 95% confidence interval.
- **Incremental Conversions**: `(p_treat - p_ctrl) * n_treat`.
- **Multiple Testing**: Benjamini-Hochberg FDR adjustment (`alpha = 0.05`) across all `25` pre-specified quartile feature cuts.
