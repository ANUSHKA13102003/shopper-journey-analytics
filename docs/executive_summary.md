# Executive Summary

**Live App:** https://shopper-journey-analytics.onrender.com | **Static Report:** https://anushka13102003.github.io/shopper-journey-analytics/

## Business Question
Where do online shoppers drop off, do new visitors return, and when does paid ad targeting actually pay back?

## Decision
**Target high-propensity segments (`F10 > 5.3` / `F4 > 10.28`, `F1 > 10.06`, `F7 > 4.834`); do not scale blanket ad spend across the full user base.**

- **Storefront prerequisite**: Fix product-page add-to-cart friction (`89.96%` drop-off) and checkout abandonment (`59.41%`) before buying broad top-of-funnel traffic.
- **Economic condition**: At an assumed value of `1,000` per conversion, blanket ad targeting breaks even only below `1.15` per treated user, whereas the top propensity quartile (`4.34%` of users) breaks even up to `15.51` per treated user (`13.5x` average).
- **Guardrails to monitor**:
  1. Ad exposure rate in treatment (`3.60%` observed in Criteo) to detect auction delivery drops.
  2. Landing-page view-to-cart (`10.04%`) and cart abandonment (`59.41%`) on paid cohorts.
  3. 28-day buyer repeat rate (`32.24%`) to confirm acquired customers retain.

## Supporting Evidence (From `outputs/*.json`)
1. **Session funnel (`23,005,603` viewed sessions, REES46 Oct-Nov 2019)**:
   - `2,309,287` sessions add to cart (`10.04%` view-to-cart; `89.96%` drop-off) and `937,336` purchase (`40.59%` cart-to-purchase; `4.07%` view-to-purchase).
   - Median time from first view to purchase is `3.12` minutes (`p25 = 1.45` min, `p75 = 6.87` min).
   - Electronics (`9,525,829` sessions) converts at `6.02%`, while `$100 - $299` entry items convert at `4.96%` vs `2.52%` under `$25`.
2. **Cohort retention (`4,359,106` new shoppers after 7-day washout)**:
   - Cumulative return reaches `27.51%` within 7 days (`3,919,628` eligible), `37.96%` within 14 days (`3,341,589` eligible), and `49.74%` within 28 days (`2,205,364` eligible).
   - Exact-day stickiness moves from `10.09%` on Day 1 to `4.59%` on Day 7 and `4.44%` on Day 28.
   - Among `274,794` full-window first-time buyers, `88,596` (`32.24%`) place a repeat order within 28 days.
3. **Randomized ad trial (`13,979,592` users, Criteo Uplift v2.1)**:
   - Deliberate 85/15 split (`11,882,655` treatment, `2,096,937` control) passes covariate balance across all 12 features (`max |SMD| = 0.0488 < 0.10`).
   - Primary conversion rises from `0.1938%` to `0.3089%`: `+1.152` incremental conversions per 1,000 users (95% CI `[+1.085, +1.219]`, `+59.45%` relative, `p = 7.31e-179`), generating `13,687` incremental conversions.
   - Across `25` Benjamini-Hochberg adjusted quantile cuts, top quartile `F10 > 5.3` / `F4 > 10.28` (`606,897` users) yields `+15.51` incremental conversions per 1,000 users (`p_BH = 8.78e-85`).
