"""Streamlit dashboard for Shopper Journey Analytics."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

OUT_DIR = Path("outputs")

st.set_page_config(
    page_title="Shopper Journey Analytics",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data
def load_json(name: str) -> dict:
    with open(OUT_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_parquet(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT_DIR / name)


def fmt_pct(val: float, digits: int = 2) -> str:
    return f"{val * 100:.{digits}f}%"


def main() -> None:
    st.title("Shopper Journey Analytics")
    st.caption(
        "Where online shoppers drop off, whether they come back, and how to test if an ad works."
    )

    required = [
        "rees46_summary.json",
        "data_quality.json",
        "funnel_summary.parquet",
        "cohorts_weekly.parquet",
        "retention_curve.parquet",
        "criteo_summary.json",
        "criteo_balance.parquet",
        "criteo_segments.parquet",
        "criteo_breakeven.parquet",
    ]
    missing = [f for f in required if not (OUT_DIR / f).exists()]
    if missing:
        st.error(f"Missing aggregated outputs: {', '.join(missing)}. Run `python run_all.py` first.")
        return

    part_a = load_json("rees46_summary.json")
    dq = load_json("data_quality.json")
    funnel_df = load_parquet("funnel_summary.parquet")
    cohorts_df = load_parquet("cohorts_weekly.parquet")
    curve_df = load_parquet("retention_curve.parquet")

    part_b = load_json("criteo_summary.json")
    balance_df = load_parquet("criteo_balance.parquet")
    segments_df = load_parquet("criteo_segments.parquet")
    breakeven_df = load_parquet("criteo_breakeven.parquet")

    tab_funnel, tab_retention, tab_exp, tab_decision = st.tabs(
        ["Funnel", "Retention", "Experiment", "Decision and Method"]
    )

    with tab_funnel:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sessions Viewed", f"{part_a['sessions_viewed']:,}")
        c2.metric("View-to-Cart", fmt_pct(part_a["view_to_cart_rate"]))
        c3.metric("Cart Abandonment", fmt_pct(part_a["cart_abandonment_rate"]))
        c4.metric(
            "Median Time to Buy",
            f"{part_a['median_minutes_to_purchase']:.1f} min",
        )

        drop_label = (
            "view to cart"
            if part_a["biggest_drop_stage"] == "view_to_cart"
            else "cart to purchase"
        )
        overall_stages = pd.DataFrame(
            {
                "Stage": ["Viewed", "Carted", "Purchased"],
                "Sessions": [
                    part_a["sessions_viewed"],
                    part_a["sessions_carted"],
                    part_a["sessions_purchased"],
                ],
            }
        )
        fig_funnel = go.Figure(
            go.Funnel(
                y=overall_stages["Stage"],
                x=overall_stages["Sessions"],
                textinfo="value+percent initial+percent previous",
            )
        )
        fig_funnel.update_layout(
            title=(
                f"Biggest drop-off is {drop_label} "
                f"({fmt_pct(part_a['biggest_drop_pct'], 1)} lost)"
            ),
            margin={"l": 10, "r": 10, "t": 50, "b": 20},
            height=340,
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

        col_l, col_r = st.columns(2)
        with col_l:
            cat_df = (
                funnel_df[funnel_df["breakdown_type"] == "category"]
                .sort_values("sessions_viewed", ascending=False)
                .head(10)
            )
            cat_df["v2p_pct"] = cat_df["view_to_purchase_rate"] * 100.0
            fig_cat = px.bar(
                cat_df.sort_values("v2p_pct"),
                x="v2p_pct",
                y="breakdown_value",
                orientation="h",
                labels={"v2p_pct": "View-to-Purchase (%)", "breakdown_value": "Category"},
                title=(
                    f"Top category {part_a['top_known_category']} converts "
                    f"at {fmt_pct(part_a['top_known_category_v2p'])}"
                ),
            )
            fig_cat.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
            st.plotly_chart(fig_cat, use_container_width=True)

        with col_r:
            pb_df = funnel_df[funnel_df["breakdown_type"] == "price_band"].sort_values("sort_order")
            pb_df["v2p_pct"] = pb_df["view_to_purchase_rate"] * 100.0
            pb_df["abandon_pct"] = pb_df["cart_abandonment_rate"] * 100.0
            fig_pb = px.bar(
                pb_df,
                x="breakdown_value",
                y="v2p_pct",
                labels={"breakdown_value": "Price Band", "v2p_pct": "View-to-Purchase (%)"},
                title="View-to-purchase conversion by entry price band",
            )
            fig_pb.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
            st.plotly_chart(fig_pb, use_container_width=True)

        col_w, col_h = st.columns(2)
        with col_w:
            wd_df = funnel_df[funnel_df["breakdown_type"] == "weekday"].sort_values("sort_order")
            wd_df["v2p_pct"] = wd_df["view_to_purchase_rate"] * 100.0
            fig_wd = px.bar(
                wd_df,
                x="breakdown_value",
                y="v2p_pct",
                labels={"breakdown_value": "Weekday", "v2p_pct": "View-to-Purchase (%)"},
                title="Session conversion by day of week",
            )
            fig_wd.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=320)
            st.plotly_chart(fig_wd, use_container_width=True)

        with col_h:
            hr_df = funnel_df[funnel_df["breakdown_type"] == "hour"].sort_values("sort_order")
            hr_df["v2p_pct"] = hr_df["view_to_purchase_rate"] * 100.0
            fig_hr = px.line(
                hr_df,
                x="breakdown_value",
                y="v2p_pct",
                markers=True,
                labels={"breakdown_value": "Hour (UTC)", "v2p_pct": "View-to-Purchase (%)"},
                title="Session conversion by hour of day (UTC)",
            )
            fig_hr.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=320)
            st.plotly_chart(fig_hr, use_container_width=True)

    with tab_retention:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Eligible New Shoppers", f"{part_a['total_eligible_cohort_users']:,}")
        r2.metric("D7 Return Rate", fmt_pct(part_a["d7_return_rate"]))
        r3.metric("D14 Return Rate", fmt_pct(part_a["d14_return_rate"]))
        r4.metric("28-Day Repeat Purchase", fmt_pct(part_a["repeat_purchase_28d_rate"]))

        st.caption(
            f"D28 return rate across {part_a['eligible_d28_users']:,} full-window users: "
            f"{fmt_pct(part_a['d28_return_rate'])}. Users first seen in the first 7 days are excluded."
        )

        curve_plot = curve_df.copy()
        curve_plot["rate_pct"] = curve_plot["rate"] * 100.0
        fig_curve = px.line(
            curve_plot,
            x="day_n",
            y="rate_pct",
            markers=True,
            labels={"day_n": "Days Since First Seen", "rate_pct": "Active Return Rate (%)"},
            title=(
                f"Exact-day retention drops from {curve_plot.iloc[0]['rate_pct']:.2f}% on D1 "
                f"to {curve_plot.iloc[-1]['rate_pct']:.2f}% on D28"
            ),
        )
        fig_curve.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
        st.plotly_chart(fig_curve, use_container_width=True)

        coh_long = cohorts_df.melt(
            id_vars=["cohort_week", "cohort_users"],
            value_vars=["d7_return_rate", "d14_return_rate", "d28_return_rate"],
            var_name="window",
            value_name="rate",
        ).dropna(subset=["rate"])
        coh_long["rate_pct"] = coh_long["rate"] * 100.0
        coh_long["window"] = coh_long["window"].str.replace("_return_rate", "").str.upper()
        fig_coh = px.line(
            coh_long,
            x="cohort_week",
            y="rate_pct",
            color="window",
            markers=True,
            labels={"cohort_week": "Cohort Week", "rate_pct": "Cumulative Return Rate (%)"},
            title="Weekly cohort cumulative return rates (full-window users only)",
        )
        fig_coh.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
        st.plotly_chart(fig_coh, use_container_width=True)

    with tab_exp:
        conv = part_b["conversion"]
        vis = part_b["visit"]
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Experiment Users", f"{part_b['total_rows']:,}")
        e2.metric("Conversion Lift / 1k", f"+{conv['abs_lift_per_1000']:.3f}")
        e3.metric("Relative Lift", f"+{conv['rel_lift'] * 100:.1f}%")
        e4.metric("Max |SMD|", f"{part_b['max_abs_smd']:.4f}")

        st.caption(
            f"Uneven 85/15 split ({part_b['treatment_share'] * 100:.2f}% treatment, "
            f"{part_b['control_share'] * 100:.2f}% control). "
            f"Visit lift: +{vis['abs_lift_per_1000']:.2f} per 1,000 (+{vis['rel_lift'] * 100:.1f}%). "
            f"Incremental conversions: {conv['incremental_conversions']:,.0f}."
        )

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            fig_smd = px.bar(
                balance_df.sort_values("abs_smd"),
                x="abs_smd",
                y="feature",
                orientation="h",
                labels={"abs_smd": "|Standardized Mean Difference|", "feature": "Feature"},
                title=f"All 12 features pass balance check (max |SMD| = {part_b['max_abs_smd']:.4f} < 0.10)",
            )
            fig_smd.add_vline(x=0.10, line_dash="dash", line_color="red")
            fig_smd.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
            st.plotly_chart(fig_smd, use_container_width=True)

        with col_b2:
            top_seg = segments_df.sort_values("abs_lift_per_1000", ascending=False).head(10).copy()
            top_seg["segment"] = top_seg["feature"] + ": " + top_seg["bin_label"]
            fig_seg = px.bar(
                top_seg.sort_values("abs_lift_per_1000"),
                x="abs_lift_per_1000",
                y="segment",
                orientation="h",
                labels={"abs_lift_per_1000": "Lift per 1,000 Treated Users", "segment": "Segment"},
                title=(
                    f"Top segments yield +{top_seg.iloc[0]['abs_lift_per_1000']:.2f} "
                    f"conversions per 1,000 (BH-adjusted)"
                ),
            )
            fig_seg.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 20}, height=360)
            st.plotly_chart(fig_seg, use_container_width=True)

        st.subheader("Break-Even Assumptions Table (No Real Ad Cost Claimed)")
        be_display = breakeven_df.copy()
        be_display["roi_pct"] = (be_display["roi"] * 100).round(1)
        st.dataframe(
            be_display[
                [
                    "value_per_conversion",
                    "cost_per_treated_user",
                    "break_even_cost_per_user",
                    "net_value_per_1000_treated",
                    "roi_pct",
                    "profitable",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    with tab_decision:
        st.subheader("Decision: Target High-Uplift Segments First, Do Not Scale Blindly")
        st.markdown(
            f"""
- **Experiment Verdict**: The ad campaign increases conversions by **+{conv['abs_lift_per_1000']:.3f} per 1,000 treated users**
  (95% CI [{conv['abs_lift_per_1000_ci_low']:.3f}, {conv['abs_lift_per_1000_ci_high']:.3f}], `p = {conv['p_value']:.2e}`).
- **Why Targeted Rollout Beats Blanket Scaling**: Overall break-even ad cost is only **{conv['abs_lift'] * 1000:.2f}**
  at an assumed value of 1,000 per conversion. In the top quartile segment (`f10 > 5.3` / `f4 > 10.28`),
  lift jumps to **+{segments_df['abs_lift_per_1000'].max():.2f} per 1,000** ({segments_df['abs_lift_per_1000'].max() / conv['abs_lift_per_1000']:.1f}x the overall average).
- **Guardrails to Monitor**:
  1. Exposure rate (`{part_b['exposure_rate_treat'] * 100:.2f}%` of treated users actually saw the ad).
  2. Cart abandonment (`{fmt_pct(part_a['cart_abandonment_rate'])}` in Part A) before increasing top-of-funnel ad spend.
  3. 28-day repeat purchase (`{fmt_pct(part_a['repeat_purchase_28d_rate'])}`) to verify incremental buyers retain.
            """
        )
        st.subheader("Data Quality & Method Summary")
        st.json(
            {
                "part_a_total_rows": dq["total_rows"],
                "part_a_date_range": f"{dq['min_event_time']} to {dq['max_event_time']}",
                "part_a_duplicates_kept_or_flagged": dq["duplicate_rows"],
                "part_a_price_le_zero": dq["price_le_zero"],
                "part_b_total_rows": part_b["total_rows"],
                "part_b_segment_cuts_tested": part_b["n_segment_cuts_tested"],
                "part_b_segment_cuts_significant_bh": part_b["n_segment_cuts_significant_bh"],
            }
        )


if __name__ == "__main__":
    main()
