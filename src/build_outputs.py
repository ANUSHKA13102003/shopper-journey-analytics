"""Execute Part A SQL queries via DuckDB and export aggregated outputs."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd


def run_part_a_sql(
    source_paths: list[Path],
    sql_dir: Path = Path("sql"),
    out_dir: Path = Path("outputs"),
    temp_dir: Path = Path("data/interim/duckdb_tmp"),
) -> dict:
    """Run numbered Part A SQL files against REES46 CSVs or Parquet fixture."""
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")
    con.execute(f"SET temp_directory = '{temp_dir.as_posix()}'")

    if len(source_paths) == 1 and source_paths[0].suffix == ".parquet":
        con.execute(
            f"CREATE TEMP VIEW events_source AS SELECT * FROM read_parquet('{source_paths[0].as_posix()}')"
        )
    else:
        files_sql = ", ".join(f"'{p.as_posix()}'" for p in source_paths)
        con.execute(
            f"""
            CREATE TEMP VIEW events_source AS
            SELECT * FROM read_csv(
                [{files_sql}],
                header=true,
                delim=',',
                columns={{
                    'event_time': 'TIMESTAMP',
                    'event_type': 'VARCHAR',
                    'product_id': 'BIGINT',
                    'category_id': 'BIGINT',
                    'category_code': 'VARCHAR',
                    'brand': 'VARCHAR',
                    'price': 'DOUBLE',
                    'user_id': 'BIGINT',
                    'user_session': 'VARCHAR'
                }}
            )
            """
        )

    funnel_sql = (sql_dir / "01_funnel.sql").read_text(encoding="utf-8")
    funnel_df = con.execute(funnel_sql).fetchdf()
    funnel_df.to_parquet(out_dir / "funnel_summary.parquet", index=False)

    cohorts_sql = (sql_dir / "02_cohorts.sql").read_text(encoding="utf-8")
    cohorts_df = con.execute(cohorts_sql).fetchdf()
    cohorts_df.to_parquet(out_dir / "cohorts_weekly.parquet", index=False)

    curve_sql = (sql_dir / "03_retention_curve_and_repeat.sql").read_text(encoding="utf-8")
    curve_all_df = con.execute(curve_sql).fetchdf()
    curve_df = curve_all_df[curve_all_df["metric_type"] == "exact_day_curve"].copy()
    repeat_df = curve_all_df[curve_all_df["metric_type"] == "repeat_purchase_28d"].copy()
    curve_df.to_parquet(out_dir / "retention_curve.parquet", index=False)

    overall = funnel_df[funnel_df["breakdown_type"] == "overall"].iloc[0]
    v2c = float(overall["view_to_cart_rate"])
    c2p = float(overall["cart_to_purchase_rate"])
    v2c_drop = 1.0 - v2c
    c2p_drop = 1.0 - c2p
    if v2c_drop >= c2p_drop:
        biggest_drop_stage = "view_to_cart"
        biggest_drop_pct = v2c_drop
    else:
        biggest_drop_stage = "cart_to_purchase"
        biggest_drop_pct = c2p_drop

    # Weighted overall D7/D14/D28 across eligible users
    def _weighted_rate(df: pd.DataFrame, ret_col: str, elig_col: str) -> float:
        denom = float(df[elig_col].sum())
        return float(df[ret_col].sum() / denom) if denom > 0 else 0.0

    repeat_row = repeat_df.iloc[0] if len(repeat_df) > 0 else None

    cats = funnel_df[
        (funnel_df["breakdown_type"] == "category")
        & (funnel_df["breakdown_value"] != "unknown")
    ].sort_values("sessions_viewed", ascending=False)
    top_cat = cats.iloc[0] if len(cats) > 0 else None

    summary = {
        "sessions_viewed": int(overall["sessions_viewed"]),
        "sessions_carted": int(overall["sessions_carted"]),
        "sessions_purchased": int(overall["sessions_purchased"]),
        "sessions_cart_abandoned": int(overall["sessions_cart_abandoned"]),
        "view_to_cart_rate": v2c,
        "cart_to_purchase_rate": c2p,
        "view_to_purchase_rate": float(overall["view_to_purchase_rate"]),
        "cart_abandonment_rate": float(overall["cart_abandonment_rate"]),
        "biggest_drop_stage": biggest_drop_stage,
        "biggest_drop_pct": float(biggest_drop_pct),
        "median_minutes_to_purchase": float(overall["median_minutes_to_purchase"]),
        "p25_minutes_to_purchase": float(overall["p25_minutes_to_purchase"]),
        "p75_minutes_to_purchase": float(overall["p75_minutes_to_purchase"]),
        "total_revenue": float(overall["total_revenue"]),
        "top_known_category": str(top_cat["breakdown_value"]) if top_cat is not None else "unknown",
        "top_known_category_sessions": int(top_cat["sessions_viewed"]) if top_cat is not None else 0,
        "top_known_category_v2p": float(top_cat["view_to_purchase_rate"]) if top_cat is not None else 0.0,
        "total_eligible_cohort_users": int(cohorts_df["cohort_users"].sum()),
        "d7_return_rate": _weighted_rate(cohorts_df, "returned_d7_users", "eligible_d7_users"),
        "d14_return_rate": _weighted_rate(cohorts_df, "returned_d14_users", "eligible_d14_users"),
        "d28_return_rate": _weighted_rate(cohorts_df, "returned_d28_users", "eligible_d28_users"),
        "eligible_d7_users": int(cohorts_df["eligible_d7_users"].sum()),
        "eligible_d14_users": int(cohorts_df["eligible_d14_users"].sum()),
        "eligible_d28_users": int(cohorts_df["eligible_d28_users"].sum()),
        "repeat_purchase_28d_eligible_buyers": int(repeat_row["eligible_users"]) if repeat_row is not None else 0,
        "repeat_purchase_28d_buyers": int(repeat_row["retained_users"]) if repeat_row is not None else 0,
        "repeat_purchase_28d_rate": float(repeat_row["rate"]) if repeat_row is not None else 0.0,
    }

    with open(out_dir / "rees46_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_static_html_report(
    out_dir: Path = Path("outputs"),
    html_path: Path = Path("docs/index.html"),
) -> Path:
    """Generate a self-contained static HTML report for GitHub Pages from outputs/."""
    import plotly.graph_objects as go
    import plotly.io as pio

    part_a = json.loads((out_dir / "rees46_summary.json").read_text(encoding="utf-8"))
    part_b = json.loads((out_dir / "criteo_summary.json").read_text(encoding="utf-8"))
    curve_df = pd.read_parquet(out_dir / "retention_curve.parquet")
    seg_df = pd.read_parquet(out_dir / "criteo_segments.parquet")

    fig_funnel = go.Figure(
        go.Funnel(
            y=["Viewed Product", "Added to Cart", "Completed Purchase"],
            x=[
                part_a["sessions_viewed"],
                part_a["sessions_carted"],
                part_a["sessions_purchased"],
            ],
            textinfo="value+percent initial+percent previous",
            marker={"color": ["#1F6FEB", "#0D5C53", "#D96B18"]},
        )
    )
    fig_funnel.update_layout(
        title=(
            f"Biggest leak is product view to add-to-cart: "
            f"{part_a['biggest_drop_pct'] * 100:.2f}% of sessions never add an item"
        ),
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        height=350,
    )

    d1_pct = float(curve_df.iloc[0]["rate"] * 100.0)
    d28_pct = float(curve_df.iloc[-1]["rate"] * 100.0)
    fig_ret = go.Figure(
        go.Scatter(
            x=curve_df["day_n"],
            y=curve_df["rate"] * 100.0,
            mode="lines+markers",
            line={"color": "#0D5C53", "width": 2.5},
            marker={"size": 6},
        )
    )
    fig_ret.update_layout(
        title=f"Exact-day return drops from {d1_pct:.2f}% on Day 1 to {d28_pct:.2f}% on Day 28",
        xaxis_title="Days Since First Visit",
        yaxis_title="Exact-Day Return Rate (%)",
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        height=350,
    )

    top_seg = seg_df.sort_values("abs_lift_per_1000", ascending=False).head(8).iloc[::-1]
    top_seg_lift = float(top_seg.iloc[-1]["abs_lift_per_1000"])
    conv = part_b["conversion"]
    fig_seg = go.Figure(
        go.Bar(
            x=top_seg["abs_lift_per_1000"],
            y=top_seg["feature"].str.upper() + " " + top_seg["bin_label"],
            orientation="h",
            marker={"color": "#D96B18"},
        )
    )
    fig_seg.update_layout(
        title=(
            f"Top quartile segments generate +{top_seg_lift:.2f} conversions per 1,000 "
            f"({top_seg_lift / conv['abs_lift_per_1000']:.1f}x population average)"
        ),
        xaxis_title="Incremental Conversions per 1,000 Treated Users",
        yaxis_title="Feature Quartile",
        margin={"l": 20, "r": 20, "t": 48, "b": 20},
        height=370,
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Shopper Journey Analytics - Static Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 1020px; margin: 0 auto; padding: 24px 18px 48px; color: #1f2328; line-height: 1.55; }}
    h1 {{ margin-bottom: 6px; }}
    h2 {{ border-bottom: 1px solid #d0d7de; padding-bottom: 6px; margin-top: 32px; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 20px; }}
    .btn {{ display: inline-block; padding: 7px 14px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 600; border: 1px solid #0D5C53; color: #0D5C53; }}
    .btn.primary {{ background: #0D5C53; color: #ffffff; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 14px; }}
    .label {{ font-size: 12px; color: #57606a; text-transform: uppercase; letter-spacing: 0.02em; }}
    .val {{ font-size: 22px; font-weight: 600; margin-top: 4px; color: #0D5C53; }}
    .takeaway {{ font-size: 14px; background: #f6f8fa; border-left: 3px solid #0D5C53; padding: 8px 12px; margin: 6px 0 18px; border-radius: 0 6px 6px 0; }}
    .decision {{ background: #eef7f5; border: 1px solid #0D5C53; border-left: 6px solid #0D5C53; border-radius: 8px; padding: 16px 20px; margin-top: 24px; }}
    .decision h3 {{ margin-top: 0; color: #0D5C53; }}
  </style>
</head>
<body>
  <h1>Shopper Journey Analytics</h1>
  <p>Where online shoppers drop off, whether new visitors return, and when paid ad targeting pays back — generated directly from aggregated DuckDB &amp; SciPy outputs (<code>outputs/</code>).</p>
  <div class="nav">
    <a class="btn primary" href="https://shopper-journey-analytics.onrender.com">Open Interactive Streamlit App</a>
    <a class="btn" href="https://github.com/ANUSHKA13102003/shopper-journey-analytics">View GitHub Repository &amp; SQL</a>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Viewed Sessions</div><div class="val">{part_a['sessions_viewed']:,}</div></div>
    <div class="card"><div class="label">View-to-Purchase</div><div class="val">{part_a['view_to_purchase_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">Cart Abandonment</div><div class="val">{part_a['cart_abandonment_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">28-Day Return Rate</div><div class="val">{part_a['d28_return_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">28-Day Repeat Buyers</div><div class="val">{part_a['repeat_purchase_28d_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">Ad Lift / 1,000 Users</div><div class="val">+{conv['abs_lift_per_1000']:.2f}</div></div>
  </div>

  <h2>1. Session Funnel Drop-Off (REES46, 109.95M Events)</h2>
  {pio.to_html(fig_funnel, full_html=False, include_plotlyjs="cdn")}
  <div class="takeaway"><strong>What this means:</strong> {part_a['biggest_drop_pct'] * 100:.2f}% of browsing sessions leave before adding an item to cart ({part_a['view_to_cart_rate'] * 100:.2f}% view-to-cart), and {part_a['cart_abandonment_rate'] * 100:.2f}% of carts abandon before payment. Median time from first view to purchase is {part_a['median_minutes_to_purchase']:.2f} minutes.</div>

  <h2>2. New-Shopper Cohort Retention (REES46, 4.36M Eligible Users)</h2>
  {pio.to_html(fig_ret, full_html=False, include_plotlyjs=False)}
  <div class="takeaway"><strong>What this means:</strong> Excluding the first 7 days as existing traffic, cumulative return reaches {part_a['d7_return_rate'] * 100:.2f}% within 7 days, {part_a['d14_return_rate'] * 100:.2f}% within 14 days, and {part_a['d28_return_rate'] * 100:.2f}% within 28 days, while {part_a['repeat_purchase_28d_rate'] * 100:.2f}% of first-time buyers repeat within 28 days.</div>

  <h2>3. Randomized Ad Uplift Experiment (Criteo v2.1, 13.98M Users)</h2>
  {pio.to_html(fig_seg, full_html=False, include_plotlyjs=False)}
  <div class="takeaway"><strong>What this means:</strong> Across an 85/15 split (max |SMD| = {part_b['max_abs_smd']:.4f}), treatment lifts overall conversion by +{conv['abs_lift_per_1000']:.2f} per 1,000 users (+{conv['rel_lift'] * 100:.1f}% relative, p = {conv['p_value']:.2e}), but top-quartile segments (F10 &gt; 5.3 / F4 &gt; 10.28) generate +{top_seg_lift:.2f} per 1,000 ({top_seg_lift / conv['abs_lift_per_1000']:.1f}x average).</div>

  <div class="decision">
    <h3>Decision: Target High-Uplift Segments First — Do Not Scale Blanket Ad Spend</h3>
    <p>At an assumed conversion value of 1,000, blanket ad targeting breaks even only below {conv['abs_lift'] * 1000:.2f} per treated user, whereas the F10/F4 top quartile breaks even up to {top_seg_lift:.2f} per user. Fix product-page add-to-cart friction ({part_a['biggest_drop_pct'] * 100:.2f}% drop-off) and checkout abandonment ({part_a['cart_abandonment_rate'] * 100:.2f}%) first, then fund targeted ad segments where expected lift clears ad cost.</p>
  </div>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    return html_path


if __name__ == "__main__":
    csvs = [Path("data/raw/rees46/2019-Oct.csv"), Path("data/raw/rees46/2019-Nov.csv")]
    res = run_part_a_sql(csvs)
    build_static_html_report()
    print(json.dumps(res, indent=2))
