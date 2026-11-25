# Executive Summary

## Business Question
Where do online shoppers drop off, do they come back, and how should a team test whether an ad campaign actually works before scaling spend?

## Key Findings (From Aggregated Outputs)
1. **Top-of-funnel browsing is the largest leak**: Across `23,005,603` viewed sessions in REES46 (Oct-Nov 2019), `89.96%` drop off before adding an item to cart (`2,309,287` carted, `10.04%` view-to-cart). Of carted sessions, `59.41%` abandon before purchase, leaving an overall `4.07%` view-to-purchase rate (`937,336` purchased sessions; median `3.12` minutes from first view to purchase).
2. **Half of new shoppers return within 28 days, and nearly a third of buyers repeat**: Excluding the first 7 days as pre-existing traffic leaves `4,359,106` new shoppers. Cumulative return rates are `27.51%` within 7 days, `37.96%` within 14 days, and `49.74%` within 28 days (exact-day retention moves from `10.09%` on D1 to `4.44%` on D28). Among `274,794` eligible first-time buyers, `32.24%` (`88,596`) purchase again within 28 days.
3. **Ad uplift is statistically real but concentrated in a small active slice**: In the Criteo Uplift v2.1 randomized trial (`13,979,592` users; `85.00%` treatment, `15.00%` control; max `|SMD| = 0.0488`), treatment lifts conversion by `+1.152` per 1,000 users (`+59.45%` relative, 95% CI `[+54.37%, +64.69%]`, `p = 7.31e-179`). However, in the top propensity segment (`f10 > 5.3` / `f4 > 10.28`, `4.34%` of users), lift is `+15.51` per 1,000 (`13.5x` the overall average).

## Decision and Conditions
- **Decision**: **Target high-uplift segments (`f10 > 5.3` / `f4 > 10.28`, `f1 > 10.06`, `f7 > 4.834`); do not scale blanket ad spend across all users.**
- **Economic condition**: At an assumed conversion value of `1,000`, overall break-even ad cost is `1.15` per treated user, whereas the top segment breaks even up to `15.51` per treated user.
- **Guardrails to monitor**:
  1. Ad exposure rate in treatment (`3.60%` observed in Criteo) to track delivery efficiency.
  2. Cart abandonment (`59.41%`) and view-to-cart (`10.04%`) on landing pages before buying more traffic.
  3. 28-day repeat purchase rate (`32.24%`) to confirm acquired shoppers retain.
