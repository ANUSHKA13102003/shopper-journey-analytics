# Experiment Design and Analysis (Part B: Criteo Uplift v2.1)

## 1. Experiment Setup
- **Dataset**: Criteo Uplift Prediction Dataset v2.1 (`13,979,592` users).
- **Randomization Split**: Deliberately uneven 85% / 15% assignment (`11,882,655` treatment vs `2,096,937` control; treatment share `85.00%`). Because the split is intentionally uneven, we do not run a 50/50 sample-ratio-mismatch test; instead we verify covariate balance across all 12 pre-treatment features (`f0` through `f11`).
- **Exposure (Delivery Compliance)**: `3.60%` of treated users were exposed to the ad (`exposure = 1`), and `0.00%` of control users were exposed. All primary inference is **Intention-to-Treat (ITT)** on `treatment = 1` vs `treatment = 0` to preserve randomization.

## 2. Randomization Balance Check
We computed Standardized Mean Differences (SMD) for all 12 anonymized features `f0`..`f11` between treatment and control:
- Maximum `|SMD|` across all 12 features is `0.0488` (`f3`), well below the standard `0.10` balance threshold.
- Conclusion: randomization is clean and balanced.

## 3. Power and Minimum Detectable Effect (MDE)
Using observed control baselines (`alpha = 0.05` two-sided, `80%` power) and observed arm sizes (`11,882,655` vs `2,096,937`):
- **Conversion (primary)**: Baseline `0.1938%` (`1.938` per 1,000 users). MDE is `0.0092` percentage points (`0.092` per 1,000 users, `4.76%` relative lift). Achieved power at the observed lift is `100.0%`.
- **Visit (secondary)**: Baseline `3.820%` (`38.20` per 1,000 users). MDE is `0.0402` percentage points (`0.402` per 1,000 users, `1.05%` relative lift). Achieved power at the observed lift is `100.0%`.

## 4. Primary and Secondary Hypothesis Tests
- **Primary (`conversion`)**:
  - Control: `4,063 / 2,096,937` (`0.1938%`)
  - Treatment: `36,711 / 11,882,655` (`0.3089%`)
  - Absolute lift: `+0.1152 pp` (`+1.152` per 1,000 treated users, 95% CI `[+1.085, +1.219]`)
  - Relative lift: `+59.45%` (95% CI `[+54.37%, +64.69%]`)
  - Incremental conversions: `13,687` (95% CI `[12,887, 14,488]`)
  - Two-proportion z-test: `z = 28.52`, `p = 7.31e-179`
- **Secondary (`visit`)**:
  - Control: `80,105 / 2,096,937` (`3.8201%`)
  - Treatment: `576,824 / 11,882,655` (`4.8543%`)
  - Absolute lift: `+1.0342 pp` (`+10.342` per 1,000 treated users, 95% CI `[+10.056, +10.629]`)
  - Relative lift: `+27.07%` (95% CI `[+26.16%, +28.00%]`)
  - Two-proportion z-test: `z = 65.25`, `p < 1e-300`

## 5. Pre-Specified Segment Cuts (Benjamini-Hochberg)
We tested `25` non-degenerate quartile cuts across `f0`..`f11` and applied Benjamini-Hochberg FDR correction (`alpha = 0.05`). All `25` cuts remain statistically significant after BH adjustment, with strong heterogeneity:
- High-propensity tail (`f10 > 5.3` and `f4 > 10.28`, ~`606,897` users, `4.34%` of population): control conversion is `3.594%`, treatment conversion is `5.145%`, yielding **`+15.51` incremental conversions per 1,000 treated users** (`+43.17%` relative lift, `p_BH = 8.78e-85`).
- High-value `f1 > 10.06` (`171,950` users): `+8.86` per 1,000 (`+29.97%` relative lift, `p_BH = 2.57e-10`).
- High-value `f7 > 4.834` (`741,443` users): `+6.86` per 1,000 (`+57.73%` relative lift, `p_BH = 1.73e-52`).

## 6. Break-Even Assumptions (No Real Ad Cost Claimed)
Because Criteo Uplift v2.1 does not include ad spend or order value, we model break-even cost per treated user as `abs_lift * value_per_conversion`:
- Overall (`+1.152` conversions per 1,000 treated users): break-even ad cost is `0.58` per treated user at `500` value/conversion, `1.15` at `1,000`, `2.30` at `2,000`, and `5.76` at `5,000`.
- In the top segment (`f10 > 5.3` / `f4 > 10.28`, `+15.51` per 1,000): break-even cost per treated user is `13.5x` higher (`7.76` at `500` value/conversion, `15.51` at `1,000`).
