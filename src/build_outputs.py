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
            y=["Viewed", "Carted", "Purchased"],
            x=[
                part_a["sessions_viewed"],
                part_a["sessions_carted"],
                part_a["sessions_purchased"],
            ],
            textinfo="value+percent initial+percent previous",
        )
    )
    fig_funnel.update_layout(
        title=f"Biggest drop-off is view to cart ({part_a['biggest_drop_pct'] * 100:.2f}% lost)",
        height=360,
    )

    fig_ret = go.Figure(
        go.Scatter(
            x=curve_df["day_n"],
            y=curve_df["rate"] * 100.0,
            mode="lines+markers",
        )
    )
    fig_ret.update_layout(
        title=(
            f"Exact-day retention drops from {curve_df.iloc[0]['rate'] * 100:.2f}% on D1 "
            f"to {curve_df.iloc[-1]['rate'] * 100:.2f}% on D28"
        ),
        xaxis_title="Days Since First Seen",
        yaxis_title="Active Return Rate (%)",
        height=360,
    )

    top_seg = seg_df.sort_values("abs_lift_per_1000", ascending=False).head(8).iloc[::-1]
    fig_seg = go.Figure(
        go.Bar(
            x=top_seg["abs_lift_per_1000"],
            y=top_seg["feature"] + ": " + top_seg["bin_label"],
            orientation="h",
        )
    )
    fig_seg.update_layout(
        title="Top Criteo Uplift segments by incremental conversions per 1,000 treated users",
        xaxis_title="Lift per 1,000 Treated Users",
        height=380,
    )

    conv = part_b["conversion"]
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Shopper Journey Analytics - Static Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 0 auto; padding: 24px; color: #1f2328; line-height: 1.55; }}
    h1, h2 {{ border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }}
    .card {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 14px; }}
    .label {{ font-size: 12px; color: #57606a; text-transform: uppercase; }}
    .val {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  </style>
</head>
<body>
  <h1>Shopper Journey Analytics</h1>
  <p>Static report generated from aggregated outputs (<code>outputs/</code>). Funnel drop-off, D7/D14/D28 retention, and A/B uplift decision on real shopper data.</p>
  <div class="grid">
    <div class="card"><div class="label">Sessions Viewed</div><div class="val">{part_a['sessions_viewed']:,}</div></div>
    <div class="card"><div class="label">View-to-Purchase</div><div class="val">{part_a['view_to_purchase_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">Cart Abandonment</div><div class="val">{part_a['cart_abandonment_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">D28 Return (Window)</div><div class="val">{part_a['d28_return_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">28d Repeat Purchase</div><div class="val">{part_a['repeat_purchase_28d_rate'] * 100:.2f}%</div></div>
    <div class="card"><div class="label">Ad Conv Lift / 1k</div><div class="val">+{conv['abs_lift_per_1000']:.3f}</div></div>
  </div>
  <h2>1. Session Funnel (REES46)</h2>
  {pio.to_html(fig_funnel, full_html=False, include_plotlyjs="cdn")}
  <h2>2. Retention Curve (REES46)</h2>
  {pio.to_html(fig_ret, full_html=False, include_plotlyjs=False)}
  <h2>3. Ad Uplift Experiment (Criteo v2.1)</h2>
  <p>Across {part_b['total_rows']:,} users (85.00% treatment, 15.00% control, max |SMD| = {part_b['max_abs_smd']:.4f}), treatment increases conversion by +{conv['abs_lift_per_1000']:.3f} per 1,000 users (+{conv['rel_lift'] * 100:.2f}% relative, p = {conv['p_value']:.2e}).</p>
  {pio.to_html(fig_seg, full_html=False, include_plotlyjs=False)}
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")

    # Export clean static PNGs for README and docs/img/
    import matplotlib.pyplot as plt

    img_dir = html_path.parent / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4.0), dpi=150)
    stages = ["Viewed", "Carted", "Purchased"]
    vals = [
        part_a["sessions_viewed"] / 1e6,
        part_a["sessions_carted"] / 1e6,
        part_a["sessions_purchased"] / 1e6,
    ]
    ax.barh(stages[::-1], vals[::-1], color=["#2da44e", "#0969da", "#1f6feb"])
    ax.set_xlabel("Sessions (Millions)")
    ax.set_title(f"Biggest drop-off is view to cart ({part_a['biggest_drop_pct'] * 100:.2f}% lost)")
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.3, i, f"{v:.2f}M", va="center")
    ax.set_xlim(0, max(vals) * 1.18)
    fig.tight_layout()
    fig.savefig(img_dir / "funnel.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.0), dpi=150)
    ax.plot(curve_df["day_n"], curve_df["rate"] * 100.0, marker="o", markersize=4, color="#1f6feb")
    ax.set_xlabel("Days Since First Seen")
    ax.set_ylabel("Active Return Rate (%)")
    ax.set_title(
        f"Exact-day retention: {curve_df.iloc[0]['rate'] * 100:.2f}% on D1 "
        f"to {curve_df.iloc[-1]['rate'] * 100:.2f}% on D28"
    )
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(img_dir / "retention.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.3), dpi=150)
    top_seg_asc = top_seg.copy()
    ax.barh(
        top_seg_asc["feature"] + ": " + top_seg_asc["bin_label"],
        top_seg_asc["abs_lift_per_1000"],
        color="#1f6feb",
    )
    ax.set_xlabel("Incremental Conversions per 1,000 Treated Users")
    ax.set_title(
        f"Top segments lift +{top_seg_asc.iloc[-1]['abs_lift_per_1000']:.2f}/1k "
        f"vs +{conv['abs_lift_per_1000']:.2f}/1k overall"
    )
    fig.tight_layout()
    fig.savefig(img_dir / "experiment.png")
    plt.close(fig)

    return html_path


if __name__ == "__main__":
    csvs = [Path("data/raw/rees46/2019-Oct.csv"), Path("data/raw/rees46/2019-Nov.csv")]
    res = run_part_a_sql(csvs)
    build_static_html_report()
    print(json.dumps(res, indent=2))
