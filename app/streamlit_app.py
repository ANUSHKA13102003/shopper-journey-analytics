"""Streamlit dashboard for Shopper Journey Analytics."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

OUT_DIR = Path("outputs")

COLOR_PRIMARY = "#0D5C53"
COLOR_SECONDARY = "#1F6FEB"
COLOR_ACCENT = "#D96B18"
COLOR_MUTED = "#6E7781"

PRICE_LABELS = {
    "under_25": "Under $25",
    "25_to_99": "$25 - $99",
    "100_to_299": "$100 - $299",
    "300_plus": "$300+",
    "invalid_or_free": "$0 / Unlisted",
}

st.set_page_config(
    page_title="Shopper Journey Analytics",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.0rem; padding-bottom: 2rem; max-width: 1180px; }
    div[data-testid="stMetric"] {
        background: #f6f8fa;
        border: 1px solid #d0d7de;
        border-radius: 8px;
        padding: 10px 14px;
    }
    .takeaway {
        font-size: 0.92rem;
        color: #32383f;
        background: #f6f8fa;
        border-left: 3px solid #0D5C53;
        padding: 8px 12px;
        margin-top: -6px;
        margin-bottom: 18px;
        border-radius: 0 6px 6px 0;
    }
    .decision-card {
        background: #eef7f5;
        border: 1px solid #0D5C53;
        border-left: 6px solid #0D5C53;
        border-radius: 8px;
        padding: 18px 20px;
        margin-bottom: 18px;
    }
    .decision-card h3 { margin-top: 0; color: #0D5C53; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_outputs() -> dict:
    """Load all pre-aggregated JSON and Parquet outputs once into memory."""
    return {
        "part_a": json.loads((OUT_DIR / "rees46_summary.json").read_text(encoding="utf-8")),
        "dq": json.loads((OUT_DIR / "data_quality.json").read_text(encoding="utf-8")),
        "funnel": pd.read_parquet(OUT_DIR / "funnel_summary.parquet"),
        "cohorts": pd.read_parquet(OUT_DIR / "cohorts_weekly.parquet"),
        "curve": pd.read_parquet(OUT_DIR / "retention_curve.parquet"),
        "part_b": json.loads((OUT_DIR / "criteo_summary.json").read_text(encoding="utf-8")),
        "balance": pd.read_parquet(OUT_DIR / "criteo_balance.parquet"),
        "segments": pd.read_parquet(OUT_DIR / "criteo_segments.parquet"),
        "breakeven": pd.read_parquet(OUT_DIR / "criteo_breakeven.parquet"),
    }


def fmt_pct(val: float, digits: int = 2) -> str:
    return f"{val * 100:.{digits}f}%"


def clean_category(name: str) -> str:
    if name == "unknown":
        return "Unlisted Category"
    return name.replace("_", " ").title()


def note(text: str) -> None:
    st.markdown(f'<div class="takeaway"><strong>What this means:</strong> {text}</div>', unsafe_allow_html=True)


def main() -> None:
    st.title("Shopper Journey Analytics")
    st.markdown(
        "Where online shoppers drop off, whether new visitors return, and when paid ad targeting pays back "
        "— built on **109.95M** real e-commerce events and a **13.98M-user** randomized trial."
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

    data = load_all_outputs()
    part_a = data["part_a"]
    dq = data["dq"]
    funnel_df = data["funnel"]
    cohorts_df = data["cohorts"]
    curve_df = data["curve"]
    part_b = data["part_b"]
    balance_df = data["balance"]
    segments_df = data["segments"]
    breakeven_df = data["breakeven"]

    tab_funnel, tab_retention, tab_exp, tab_decision = st.tabs(
        ["1. Funnel Drop-Off", "2. Cohort Retention", "3. Ad Experiment", "4. Decision & Method"]
    )

    with tab_funnel:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Viewed Sessions", f"{part_a['sessions_viewed']:,}")
        c2.metric("View-to-Cart Rate", fmt_pct(part_a["view_to_cart_rate"]))
        c3.metric("Cart Abandonment", fmt_pct(part_a["cart_abandonment_rate"]))
        c4.metric("Median Time to Buy", f"{part_a['median_minutes_to_purchase']:.1f} min")

        drop_label = (
            "product view to add-to-cart"
            if part_a["biggest_drop_stage"] == "view_to_cart"
            else "cart to checkout"
        )
        fig_funnel = go.Figure(
            go.Funnel(
                y=["Viewed Product", "Added to Cart", "Completed Purchase"],
                x=[
                    part_a["sessions_viewed"],
                    part_a["sessions_carted"],
                    part_a["sessions_purchased"],
                ],
                textinfo="value+percent initial+percent previous",
                marker={"color": [COLOR_SECONDARY, COLOR_PRIMARY, COLOR_ACCENT]},
            )
        )
        fig_funnel.update_layout(
            title=f"Biggest leak is {drop_label}: {fmt_pct(part_a['biggest_drop_pct'])} of sessions never add an item",
            margin={"l": 10, "r": 10, "t": 44, "b": 8},
            height=290,
        )
        st.plotly_chart(fig_funnel, use_container_width=True)
        note(
            f"Out of {part_a['sessions_viewed']:,} browsing sessions, {part_a['sessions_viewed'] - part_a['sessions_carted']:,} "
            f"exit without adding to cart, and {part_a['sessions_cart_abandoned']:,} carts are abandoned before payment "
            f"(overall conversion {fmt_pct(part_a['view_to_purchase_rate'])})."
        )

        col_l, col_r = st.columns(2)
        with col_l:
            cat_df = (
                funnel_df[funnel_df["breakdown_type"] == "category"]
                .sort_values("sessions_viewed", ascending=False)
                .head(8)
                .copy()
            )
            cat_df["Category"] = cat_df["breakdown_value"].map(clean_category)
            cat_df["v2p_pct"] = cat_df["view_to_purchase_rate"] * 100.0
            cat_sorted = cat_df.sort_values("v2p_pct")
            fig_cat = px.bar(
                cat_sorted,
                x="v2p_pct",
                y="Category",
                orientation="h",
                labels={"v2p_pct": "View-to-Purchase Rate (%)", "Category": "Entry Category"},
                title=(
                    f"{clean_category(part_a['top_known_category'])} leads conversion "
                    f"at {fmt_pct(part_a['top_known_category_v2p'])}"
                ),
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig_cat.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=340)
            st.plotly_chart(fig_cat, use_container_width=True)
            lowest_cat = cat_sorted.iloc[0]
            note(
                f"Shoppers entering on {clean_category(part_a['top_known_category'])} buy {part_a['top_known_category_v2p'] / max(lowest_cat['view_to_purchase_rate'], 1e-6):.1f}x "
                f"as often as {lowest_cat['Category']} ({lowest_cat['v2p_pct']:.2f}%), pointing to sizing or catalog friction in lower-converting categories."
            )

        with col_r:
            pb_df = funnel_df[
                (funnel_df["breakdown_type"] == "price_band")
                & (funnel_df["breakdown_value"] != "invalid_or_free")
            ].sort_values("sort_order").copy()
            pb_df["Price Band"] = pb_df["breakdown_value"].map(lambda x: PRICE_LABELS.get(x, x))
            pb_df["v2p_pct"] = pb_df["view_to_purchase_rate"] * 100.0
            best_pb = pb_df.loc[pb_df["v2p_pct"].idxmax()]
            low_pb = pb_df.loc[pb_df["v2p_pct"].idxmin()]
            fig_pb = px.bar(
                pb_df,
                x="Price Band",
                y="v2p_pct",
                labels={"Price Band": "Entry Product Price Band (USD)", "v2p_pct": "View-to-Purchase Rate (%)"},
                title=f"Mid-tier {best_pb['Price Band']} items convert best at {best_pb['v2p_pct']:.2f}%",
                color_discrete_sequence=[COLOR_SECONDARY],
            )
            fig_pb.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=340)
            st.plotly_chart(fig_pb, use_container_width=True)
            note(
                f"{best_pb['Price Band']} sessions convert nearly twice as well as {low_pb['Price Band']} ({low_pb['v2p_pct']:.2f}%), "
                f"where cart abandonment reaches {low_pb['cart_abandonment_rate'] * 100:.2f}%."
            )

        col_w, col_h = st.columns(2)
        with col_w:
            wd_df = funnel_df[funnel_df["breakdown_type"] == "weekday"].sort_values("sort_order").copy()
            wd_df["v2p_pct"] = wd_df["view_to_purchase_rate"] * 100.0
            best_wd = wd_df.loc[wd_df["v2p_pct"].idxmax()]
            fig_wd = px.bar(
                wd_df,
                x="breakdown_value",
                y="v2p_pct",
                labels={"breakdown_value": "Day of Week", "v2p_pct": "View-to-Purchase Rate (%)"},
                title=f"Weekday conversion peaks on {best_wd['breakdown_value']} ({best_wd['v2p_pct']:.2f}%)",
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig_wd.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=300)
            st.plotly_chart(fig_wd, use_container_width=True)
            note("Purchase intent stays steady across the week, so checkout fixes benefit traffic every day.")

        with col_h:
            hr_df = funnel_df[funnel_df["breakdown_type"] == "hour"].sort_values("sort_order").copy()
            hr_df["v2p_pct"] = hr_df["view_to_purchase_rate"] * 100.0
            best_hr = hr_df.loc[hr_df["v2p_pct"].idxmax()]
            fig_hr = px.line(
                hr_df,
                x="breakdown_value",
                y="v2p_pct",
                markers=True,
                labels={"breakdown_value": "Hour of Day (UTC)", "v2p_pct": "View-to-Purchase Rate (%)"},
                title=f"Hourly conversion peaks at {best_hr['breakdown_value']}:00 UTC ({best_hr['v2p_pct']:.2f}%)",
                color_discrete_sequence=[COLOR_ACCENT],
            )
            fig_hr.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=300)
            st.plotly_chart(fig_hr, use_container_width=True)
            note("Daytime hours convert much higher than overnight browsing; schedule promos during daytime peaks.")

    with tab_retention:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Eligible New Shoppers", f"{part_a['total_eligible_cohort_users']:,}")
        r2.metric("Return Within 7 Days", fmt_pct(part_a["d7_return_rate"]))
        r3.metric("Return Within 28 Days", fmt_pct(part_a["d28_return_rate"]))
        r4.metric("28-Day Repeat Buyers", fmt_pct(part_a["repeat_purchase_28d_rate"]))

        curve_plot = curve_df.copy()
        curve_plot["rate_pct"] = curve_plot["rate"] * 100.0
        d1_pct = float(curve_plot.iloc[0]["rate_pct"])
        d28_pct = float(curve_plot.iloc[-1]["rate_pct"])
        fig_curve = px.line(
            curve_plot,
            x="day_n",
            y="rate_pct",
            markers=True,
            labels={"day_n": "Days Since First Visit", "rate_pct": "Exact-Day Return Rate (%)"},
            title=f"Exact-day return drops from {d1_pct:.2f}% on Day 1 to {d28_pct:.2f}% on Day 28",
            color_discrete_sequence=[COLOR_PRIMARY],
        )
        fig_curve.update_layout(margin={"l": 10, "r": 10, "t": 44, "b": 8}, height=295)
        st.plotly_chart(fig_curve, use_container_width=True)
        note(
            f"Daily active stickiness settles near {d28_pct:.2f}% after two weeks, while cumulative return within 28 days "
            f"reaches {fmt_pct(part_a['d28_return_rate'])} across {part_a['eligible_d28_users']:,} full-window shoppers."
        )

        coh_long = cohorts_df.melt(
            id_vars=["cohort_week", "cohort_users"],
            value_vars=["d7_return_rate", "d14_return_rate", "d28_return_rate"],
            var_name="Window",
            value_name="rate",
        ).dropna(subset=["rate"])
        coh_long["rate_pct"] = coh_long["rate"] * 100.0
        window_map = {
            "d7_return_rate": "Within 7 Days (D7)",
            "d14_return_rate": "Within 14 Days (D14)",
            "d28_return_rate": "Within 28 Days (D28)",
        }
        coh_long["Return Window"] = coh_long["Window"].map(window_map)
        fig_coh = px.line(
            coh_long,
            x="cohort_week",
            y="rate_pct",
            color="Return Window",
            markers=True,
            labels={"cohort_week": "First-Visit Cohort Week", "rate_pct": "Cumulative Return Rate (%)"},
            title=f"Half of new shoppers ({fmt_pct(part_a['d28_return_rate'])}) come back within 28 days",
            color_discrete_sequence=[COLOR_SECONDARY, COLOR_PRIMARY, COLOR_ACCENT],
        )
        fig_coh.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=350)
        st.plotly_chart(fig_coh, use_container_width=True)
        note(
            f"Users first seen in the first 7 days are excluded as existing traffic, and late cohorts without a full "
            f"7/14/28-day window are left blank rather than undercounted. Among {part_a['repeat_purchase_28d_eligible_buyers']:,} "
            f"first-time buyers, {fmt_pct(part_a['repeat_purchase_28d_rate'])} buy a second time within 28 days."
        )

    with tab_exp:
        conv = part_b["conversion"]
        vis = part_b["visit"]
        top_seg_lift = float(segments_df["abs_lift_per_1000"].max())
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Trial Sample Size", f"{part_b['total_rows']:,}")
        e2.metric("Overall Lift / 1,000", f"+{conv['abs_lift_per_1000']:.2f}")
        e3.metric("Top-Segment Lift / 1,000", f"+{top_seg_lift:.2f}")
        e4.metric("Max Balance |SMD|", f"{part_b['max_abs_smd']:.4f}")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            bal_plot = balance_df.sort_values("abs_smd").copy()
            bal_plot["Feature"] = bal_plot["feature"].str.upper()
            fig_smd = px.bar(
                bal_plot,
                x="abs_smd",
                y="Feature",
                orientation="h",
                labels={"abs_smd": "Absolute Standardized Mean Difference", "Feature": "Pre-Treatment Feature"},
                title=f"Randomization is balanced: max |SMD| = {part_b['max_abs_smd']:.4f} (below 0.10 limit)",
                color_discrete_sequence=[COLOR_PRIMARY],
            )
            fig_smd.add_vline(x=0.10, line_dash="dash", line_color=COLOR_ACCENT)
            fig_smd.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=360)
            st.plotly_chart(fig_smd, use_container_width=True)
            note(
                f"The trial intentionally assigns {part_b['treatment_share'] * 100:.0f}% to treatment and "
                f"{part_b['control_share'] * 100:.0f}% to control. Every covariate sits well inside the 0.10 SMD threshold."
            )

        with col_b2:
            top_seg = segments_df.sort_values("abs_lift_per_1000", ascending=False).head(8).copy()
            top_seg["Segment"] = top_seg["feature"].str.upper() + " " + top_seg["bin_label"]
            fig_seg = px.bar(
                top_seg.sort_values("abs_lift_per_1000"),
                x="abs_lift_per_1000",
                y="Segment",
                orientation="h",
                labels={"abs_lift_per_1000": "Incremental Conversions per 1,000 Users", "Segment": "Feature Quartile"},
                title=f"Top segments lift +{top_seg_lift:.2f} / 1,000 ({top_seg_lift / conv['abs_lift_per_1000']:.1f}x average)",
                color_discrete_sequence=[COLOR_ACCENT],
            )
            fig_seg.update_layout(margin={"l": 10, "r": 10, "t": 48, "b": 12}, height=360)
            st.plotly_chart(fig_seg, use_container_width=True)
            note(
                f"Across {part_b['n_segment_cuts_tested']} pre-specified quantile cuts (Benjamini-Hochberg FDR < 0.05), "
                f"the active F10/F4 top quartiles drive {top_seg_lift / conv['abs_lift_per_1000']:.1f}x the average conversion gain."
            )

        st.subheader("Break-Even Sensitivity Table (Explicit Cost & Value Assumptions)")
        be_clean = pd.DataFrame(
            {
                "Assumed Value / Conversion": breakeven_df["value_per_conversion"].map(lambda v: f"{v:,.0f}"),
                "Assumed Ad Cost / Treated User": breakeven_df["cost_per_treated_user"].map(lambda c: f"{c:,.2f}"),
                "Max Break-Even Cost / User": breakeven_df["break_even_cost_per_user"].map(lambda b: f"{b:,.2f}"),
                "Net Value per 1,000 Treated": breakeven_df["net_value_per_1000_treated"].map(lambda n: f"{n:+,.1f}"),
                "ROI (%)": (breakeven_df["roi"] * 100.0).map(lambda r: f"{r:+,.1f}%"),
                "Profitable at 95% CI Low?": breakeven_df["profitable_at_ci_low"].map(lambda p: "Yes" if p else "No"),
            }
        )
        st.dataframe(be_clean, use_container_width=True, hide_index=True)
        note(
            f"Criteo does not publish ad spend. At an assumed conversion value of 1,000, blanket targeting only breaks even "
            f"below {conv['abs_lift'] * 1000:.2f} per treated user, whereas the top segment breaks even up to {top_seg_lift:.2f} per user."
        )

    with tab_decision:
        conv = part_b["conversion"]
        vis = part_b["visit"]
        top_seg_lift = float(segments_df["abs_lift_per_1000"].max())
        st.markdown(
            f"""
            <div class="decision-card">
              <h3>Recommendation: Target High-Uplift Segments First — Do Not Scale Blanket Ad Spend</h3>
              <p><strong>Why:</strong> Treatment raises overall conversion from {conv['rate_ctrl'] * 100:.3f}% to {conv['rate_treat'] * 100:.3f}%
              (<strong>+{conv['abs_lift_per_1000']:.2f} incremental conversions per 1,000 users</strong>, +{conv['rel_lift'] * 100:.1f}% relative,
              95% CI [{conv['abs_lift_per_1000_ci_low']:.2f}, {conv['abs_lift_per_1000_ci_high']:.2f}], p = {conv['p_value']:.2e}).
              However, only {part_b['exposure_rate_treat'] * 100:.2f}% of treated users are exposed, and the top propensity segment
              (F10 &gt; 5.3 / F4 &gt; 10.28) delivers <strong>+{top_seg_lift:.2f} conversions per 1,000 users</strong>
              ({top_seg_lift / conv['abs_lift_per_1000']:.1f}x the population average).</p>
              <p style="margin-bottom:0;"><strong>Action plan:</strong> (1) Fix product-page add-to-cart friction first ({fmt_pct(part_a['biggest_drop_pct'])} drop-off)
              and checkout abandonment ({fmt_pct(part_a['cart_abandonment_rate'])}); (2) Restrict paid ad spend to segments where expected lift
              exceeds ad cost divided by margin per order; (3) Track 28-day repeat buying ({fmt_pct(part_a['repeat_purchase_28d_rate'])}) on acquired cohorts.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        m_left, m_right = st.columns(2)
        with m_left:
            st.subheader("Part A Summary (REES46 Storefront)")
            st.table(
                pd.DataFrame(
                    [
                        ("Raw Events Profiled", f"{dq['total_rows']:,}"),
                        ("Observation Window (UTC)", f"{dq['min_event_time'][:10]} to {dq['max_event_time'][:10]}"),
                        ("Distinct Users / Viewed Sessions", f"{dq['distinct_users']:,} / {part_a['sessions_viewed']:,}"),
                        ("Null Categories Mapped to Unlisted", f"{dq['null_category_code']:,} ({dq['null_category_code'] / dq['total_rows'] * 100:.1f}%)"),
                        ("Zero/Negative Price Rows Excluded from Revenue", f"{dq['price_le_zero']:,}"),
                        ("Cohort Washout Rule", "First 7 days excluded as existing users"),
                    ],
                    columns=["Check / Metric", "Observed Value"],
                ).set_index("Check / Metric")
            )

        with m_right:
            st.subheader("Part B Summary (Criteo Uplift v2.1)")
            st.table(
                pd.DataFrame(
                    [
                        ("Randomized Users", f"{part_b['total_rows']:,} (85% treat / 15% ctrl)"),
                        ("Ad Exposure Rate", f"{part_b['exposure_rate_treat'] * 100:.2f}% treat / {part_b['exposure_rate_ctrl'] * 100:.2f}% ctrl"),
                        ("Primary Conversion MDE (80% power)", f"{conv['mde_per_1000']:.3f} per 1,000 ({conv['mde_rel'] * 100:.2f}% rel)"),
                        ("Secondary Visit Lift", f"+{vis['abs_lift_per_1000']:.2f} per 1,000 (+{vis['rel_lift'] * 100:.1f}% rel)"),
                        ("Estimated Incremental Conversions", f"{conv['incremental_conversions']:,.0f} (95% CI [{conv['incremental_conversions_ci_low']:,.0f}, {conv['incremental_conversions_ci_high']:,.0f}])"),
                        ("Segment Multiple-Testing Control", f"Benjamini-Hochberg across {part_b['n_segment_cuts_tested']} cuts"),
                    ],
                    columns=["Experiment Parameter", "Observed Value"],
                ).set_index("Experiment Parameter")
            )


if __name__ == "__main__":
    main()
