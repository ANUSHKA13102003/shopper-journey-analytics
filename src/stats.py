"""Statistical analysis for Part B: Criteo Uplift randomized trial."""

from __future__ import annotations

import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

FEATURES = [f"f{i}" for i in range(12)]


def two_proportion_z_test(
    conv_t: int,
    n_t: int,
    conv_c: int,
    n_c: int,
    alpha: float = 0.05,
) -> dict[str, float | int]:
    """Run a two-proportion z-test with Wald 95% CI and log-RR relative lift CI."""
    if n_t <= 0 or n_c <= 0:
        raise ValueError("Arm sample sizes must be positive.")

    p_t = conv_t / n_t
    p_c = conv_c / n_c
    abs_lift = p_t - p_c

    z_crit = float(norm.ppf(1.0 - alpha / 2.0))
    se_unpooled = math.sqrt((p_t * (1.0 - p_t)) / n_t + (p_c * (1.0 - p_c)) / n_c)
    ci_low = abs_lift - z_crit * se_unpooled
    ci_high = abs_lift + z_crit * se_unpooled

    p_pool = (conv_t + conv_c) / (n_t + n_c)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_t + 1.0 / n_c))
    if se_pool > 0:
        z_stat = abs_lift / se_pool
        p_value = float(2.0 * norm.sf(abs(z_stat)))
    else:
        z_stat = 0.0
        p_value = 1.0

    if p_c > 0 and p_t > 0:
        rel_lift = (p_t - p_c) / p_c
        se_log_rr = math.sqrt((1.0 - p_t) / (n_t * p_t) + (1.0 - p_c) / (n_c * p_c))
        rr = p_t / p_c
        rel_ci_low = rr * math.exp(-z_crit * se_log_rr) - 1.0
        rel_ci_high = rr * math.exp(z_crit * se_log_rr) - 1.0
    else:
        rel_lift = 0.0
        rel_ci_low = 0.0
        rel_ci_high = 0.0

    return {
        "n_treat": int(n_t),
        "n_ctrl": int(n_c),
        "conv_treat": int(conv_t),
        "conv_ctrl": int(conv_c),
        "rate_treat": float(p_t),
        "rate_ctrl": float(p_c),
        "abs_lift": float(abs_lift),
        "abs_lift_ci_low": float(ci_low),
        "abs_lift_ci_high": float(ci_high),
        "abs_lift_per_1000": float(abs_lift * 1000.0),
        "abs_lift_per_1000_ci_low": float(ci_low * 1000.0),
        "abs_lift_per_1000_ci_high": float(ci_high * 1000.0),
        "rel_lift": float(rel_lift),
        "rel_lift_ci_low": float(rel_ci_low),
        "rel_lift_ci_high": float(rel_ci_high),
        "incremental_conversions": float(abs_lift * n_t),
        "incremental_conversions_ci_low": float(ci_low * n_t),
        "incremental_conversions_ci_high": float(ci_high * n_t),
        "z_stat": float(z_stat),
        "p_value": float(p_value),
    }


def compute_mde_and_power(
    p_baseline: float,
    n_treat: int,
    n_ctrl: int,
    alpha: float = 0.05,
    target_power: float = 0.80,
    observed_lift: float | None = None,
) -> dict[str, float]:
    """Compute MDE at target power and achieved power for an observed lift."""
    z_alpha = float(norm.ppf(1.0 - alpha / 2.0))
    z_beta = float(norm.ppf(target_power))
    se_null = math.sqrt(p_baseline * (1.0 - p_baseline) * (1.0 / n_treat + 1.0 / n_ctrl))
    mde_abs = (z_alpha + z_beta) * se_null
    mde_rel = mde_abs / p_baseline if p_baseline > 0 else 0.0

    achieved_power = float("nan")
    if observed_lift is not None and se_null > 0:
        p_t = max(0.0, min(1.0, p_baseline + observed_lift))
        se_alt = math.sqrt(
            (p_t * (1.0 - p_t)) / n_treat + (p_baseline * (1.0 - p_baseline)) / n_ctrl
        )
        if se_alt > 0:
            z_effect = abs(observed_lift) / se_alt
            achieved_power = float(
                norm.sf(z_alpha - z_effect) + norm.cdf(-z_alpha - z_effect)
            )

    return {
        "baseline_rate": float(p_baseline),
        "alpha": float(alpha),
        "target_power": float(target_power),
        "mde_abs": float(mde_abs),
        "mde_per_1000": float(mde_abs * 1000.0),
        "mde_rel": float(mde_rel),
        "achieved_power": float(achieved_power),
    }


def compute_smd(mean_t: float, var_t: float, mean_c: float, var_c: float) -> float:
    """Compute standardized mean difference between treatment and control."""
    pooled_sd = math.sqrt(max(0.0, (var_t + var_c) / 2.0))
    if pooled_sd == 0.0:
        return 0.0
    return float((mean_t - mean_c) / pooled_sd)


def benjamini_hochberg(p_values: list[float] | np.ndarray) -> np.ndarray:
    """Apply Benjamini-Hochberg FDR adjustment and return adjusted p-values."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    sorted_p = p[order]
    ranks = np.arange(1, m + 1, dtype=float)
    adj_sorted = sorted_p * (m / ranks)
    # Enforce monotonicity from largest p-value down to smallest
    adj_sorted = np.minimum.accumulate(adj_sorted[::-1])[::-1]
    adj_sorted = np.clip(adj_sorted, 0.0, 1.0)
    adj = np.empty_like(adj_sorted)
    adj[order] = adj_sorted
    return adj


def build_breakeven_table(
    abs_lift: float,
    abs_lift_ci_low: float,
    abs_lift_ci_high: float,
    values_per_conv: list[float] | None = None,
    costs_per_user: list[float] | None = None,
) -> pd.DataFrame:
    """Build an explicit break-even sensitivity table over assumed conversion values and ad costs."""
    if values_per_conv is None:
        values_per_conv = [500.0, 1000.0, 2000.0, 5000.0]
    if costs_per_user is None:
        costs_per_user = [0.5, 1.0, 2.0, 5.0]

    rows = []
    inc_per_1000 = abs_lift * 1000.0
    inc_per_1000_low = abs_lift_ci_low * 1000.0
    for v in values_per_conv:
        be_cost = abs_lift * v
        be_cost_low = abs_lift_ci_low * v
        for c in costs_per_user:
            gross_per_1000 = inc_per_1000 * v
            spend_per_1000 = 1000.0 * c
            net_per_1000 = gross_per_1000 - spend_per_1000
            roi = (net_per_1000 / spend_per_1000) if spend_per_1000 > 0 else 0.0
            net_low_per_1000 = inc_per_1000_low * v - spend_per_1000
            rows.append(
                {
                    "value_per_conversion": float(v),
                    "cost_per_treated_user": float(c),
                    "break_even_cost_per_user": float(be_cost),
                    "break_even_cost_ci_low": float(be_cost_low),
                    "gross_value_per_1000_treated": float(gross_per_1000),
                    "spend_per_1000_treated": float(spend_per_1000),
                    "net_value_per_1000_treated": float(net_per_1000),
                    "net_value_ci_low_per_1000": float(net_low_per_1000),
                    "roi": float(roi),
                    "profitable": bool(net_per_1000 > 0),
                    "profitable_at_ci_low": bool(net_low_per_1000 > 0),
                }
            )
    return pd.DataFrame(rows)


def analyze_criteo(csv_gz_path: str | Path, out_dir: str | Path = "outputs") -> dict:
    """Run full Part B statistical analysis on Criteo Uplift via DuckDB and save outputs."""
    csv_path = Path(csv_gz_path).as_posix()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()

    # 1. Overall counts and arm metrics
    overall_df = con.execute(
        f"""
        SELECT
            COUNT(*)::BIGINT AS total_rows,
            SUM(CASE WHEN treatment = 1 THEN 1 ELSE 0 END)::BIGINT AS n_treat,
            SUM(CASE WHEN treatment = 0 THEN 1 ELSE 0 END)::BIGINT AS n_ctrl,
            SUM(CASE WHEN treatment = 1 THEN conversion ELSE 0 END)::BIGINT AS conv_treat,
            SUM(CASE WHEN treatment = 0 THEN conversion ELSE 0 END)::BIGINT AS conv_ctrl,
            SUM(CASE WHEN treatment = 1 THEN visit ELSE 0 END)::BIGINT AS visit_treat,
            SUM(CASE WHEN treatment = 0 THEN visit ELSE 0 END)::BIGINT AS visit_ctrl,
            SUM(CASE WHEN treatment = 1 THEN exposure ELSE 0 END)::BIGINT AS exp_treat,
            SUM(CASE WHEN treatment = 0 THEN exposure ELSE 0 END)::BIGINT AS exp_ctrl
        FROM read_csv_auto('{csv_path}')
        """
    ).fetchdf()
    row = overall_df.iloc[0]
    total_rows = int(row["total_rows"])
    n_treat = int(row["n_treat"])
    n_ctrl = int(row["n_ctrl"])

    conv_res = two_proportion_z_test(
        int(row["conv_treat"]), n_treat, int(row["conv_ctrl"]), n_ctrl
    )
    visit_res = two_proportion_z_test(
        int(row["visit_treat"]), n_treat, int(row["visit_ctrl"]), n_ctrl
    )
    conv_power = compute_mde_and_power(
        conv_res["rate_ctrl"], n_treat, n_ctrl, observed_lift=conv_res["abs_lift"]
    )
    visit_power = compute_mde_and_power(
        visit_res["rate_ctrl"], n_treat, n_ctrl, observed_lift=visit_res["abs_lift"]
    )

    # 2. Randomization balance (SMD for f0..f11)
    agg_exprs = []
    for f in FEATURES:
        agg_exprs.append(f"AVG({f}) FILTER (WHERE treatment = 1) AS {f}_mean_t")
        agg_exprs.append(f"VAR_SAMP({f}) FILTER (WHERE treatment = 1) AS {f}_var_t")
        agg_exprs.append(f"AVG({f}) FILTER (WHERE treatment = 0) AS {f}_mean_c")
        agg_exprs.append(f"VAR_SAMP({f}) FILTER (WHERE treatment = 0) AS {f}_var_c")

    bal_raw = con.execute(
        f"SELECT {', '.join(agg_exprs)} FROM read_csv_auto('{csv_path}')"
    ).fetchdf().iloc[0]

    balance_rows = []
    for f in FEATURES:
        mt = float(bal_raw[f"{f}_mean_t"])
        vt = float(bal_raw[f"{f}_var_t"])
        mc = float(bal_raw[f"{f}_mean_c"])
        vc = float(bal_raw[f"{f}_var_c"])
        smd = compute_smd(mt, vt, mc, vc)
        balance_rows.append(
            {
                "feature": f,
                "mean_treat": mt,
                "mean_ctrl": mc,
                "std_treat": math.sqrt(max(0.0, vt)),
                "std_ctrl": math.sqrt(max(0.0, vc)),
                "smd": smd,
                "abs_smd": abs(smd),
            }
        )
    balance_df = pd.DataFrame(balance_rows)
    balance_df.to_parquet(out_path / "criteo_balance.parquet", index=False)

    # 3. Pre-specified quantile segment cuts on f0..f11
    q_exprs = [f"QUANTILE_CONT({f}, [0.25, 0.5, 0.75]) AS {f}_q" for f in FEATURES]
    q_row = con.execute(
        f"SELECT {', '.join(q_exprs)} FROM read_csv_auto('{csv_path}')"
    ).fetchdf().iloc[0]

    # Build a single SQL query with CASE WHEN bins for all 12 features using UNPIVOT / UNION ALL
    case_selects = []
    for f in FEATURES:
        q25, q50, q75 = [float(x) for x in q_row[f"{f}_q"]]
        # If feature is heavily tied at q25/q50/q75, we still define clean non-overlapping ranges
        if q25 == q50 == q75:
            expr = f"""
            SELECT '{f}' AS feature,
                   CASE WHEN {f} <= {q25} THEN 'Q1-Q3 (<= {q25:.4g})'
                        ELSE 'Q4 (> {q25:.4g})' END AS bin_label,
                   CASE WHEN {f} <= {q25} THEN 1 ELSE 4 END AS bin_order,
                   treatment, conversion
            FROM criteo_src
            """
        elif q25 == q50:
            expr = f"""
            SELECT '{f}' AS feature,
                   CASE WHEN {f} <= {q50} THEN 'Q1-Q2 (<= {q50:.4g})'
                        WHEN {f} <= {q75} THEN 'Q3 ({q50:.4g} to {q75:.4g})'
                        ELSE 'Q4 (> {q75:.4g})' END AS bin_label,
                   CASE WHEN {f} <= {q50} THEN 1 WHEN {f} <= {q75} THEN 3 ELSE 4 END AS bin_order,
                   treatment, conversion
            FROM criteo_src
            """
        else:
            expr = f"""
            SELECT '{f}' AS feature,
                   CASE WHEN {f} <= {q25} THEN 'Q1 (<= {q25:.4g})'
                        WHEN {f} <= {q50} THEN 'Q2 ({q25:.4g} to {q50:.4g})'
                        WHEN {f} <= {q75} THEN 'Q3 ({q50:.4g} to {q75:.4g})'
                        ELSE 'Q4 (> {q75:.4g})' END AS bin_label,
                   CASE WHEN {f} <= {q25} THEN 1
                        WHEN {f} <= {q50} THEN 2
                        WHEN {f} <= {q75} THEN 3
                        ELSE 4 END AS bin_order,
                   treatment, conversion
            FROM criteo_src
            """
        case_selects.append(
            f"""
            SELECT feature, bin_label, MIN(bin_order) AS bin_order,
                   SUM(CASE WHEN treatment = 1 THEN 1 ELSE 0 END)::BIGINT AS n_treat,
                   SUM(CASE WHEN treatment = 0 THEN 1 ELSE 0 END)::BIGINT AS n_ctrl,
                   SUM(CASE WHEN treatment = 1 THEN conversion ELSE 0 END)::BIGINT AS conv_treat,
                   SUM(CASE WHEN treatment = 0 THEN conversion ELSE 0 END)::BIGINT AS conv_ctrl
            FROM ({expr})
            GROUP BY feature, bin_label
            """
        )

    con.execute(
        f"CREATE TEMP VIEW criteo_src AS SELECT {', '.join(FEATURES)}, treatment, conversion FROM read_csv_auto('{csv_path}')"
    )
    seg_raw = con.execute(" UNION ALL ".join(case_selects)).fetchdf()
    seg_raw = seg_raw.sort_values(["feature", "bin_order"]).reset_index(drop=True)

    seg_rows = []
    for _, r in seg_raw.iterrows():
        if int(r["n_treat"]) == 0 or int(r["n_ctrl"]) == 0:
            continue
        res = two_proportion_z_test(
            int(r["conv_treat"]),
            int(r["n_treat"]),
            int(r["conv_ctrl"]),
            int(r["n_ctrl"]),
        )
        seg_rows.append(
            {
                "feature": r["feature"],
                "bin_label": r["bin_label"],
                "bin_order": int(r["bin_order"]),
                **res,
            }
        )

    seg_df = pd.DataFrame(seg_rows)
    seg_df["p_value_bh"] = benjamini_hochberg(seg_df["p_value"].to_numpy())
    seg_df["significant_bh"] = seg_df["p_value_bh"] < 0.05
    seg_df.to_parquet(out_path / "criteo_segments.parquet", index=False)

    # 4. Break-even assumptions table
    be_df = build_breakeven_table(
        conv_res["abs_lift"],
        conv_res["abs_lift_ci_low"],
        conv_res["abs_lift_ci_high"],
    )
    be_df.to_parquet(out_path / "criteo_breakeven.parquet", index=False)

    summary = {
        "dataset": "Criteo Uplift v2.1",
        "total_rows": total_rows,
        "treatment_share": float(n_treat / total_rows),
        "control_share": float(n_ctrl / total_rows),
        "exposure_rate_treat": float(int(row["exp_treat"]) / n_treat),
        "exposure_rate_ctrl": float(int(row["exp_ctrl"]) / n_ctrl),
        "max_abs_smd": float(balance_df["abs_smd"].max()),
        "conversion": {**conv_res, **conv_power},
        "visit": {**visit_res, **visit_power},
        "n_segment_cuts_tested": len(seg_df),
        "n_segment_cuts_significant_bh": int(seg_df["significant_bh"].sum()),
    }
    with open(out_path / "criteo_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    result = analyze_criteo("data/raw/criteo-research-uplift-v2.1.csv.gz", "outputs")
    print(json.dumps(result, indent=2))
