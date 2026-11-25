"""Tests for Part A SQL logic on the real sample fixture and aggregated outputs."""

from pathlib import Path

import pandas as pd

from src.build_outputs import run_part_a_sql

FIXTURE = Path("tests/fixtures/rees46_sample.parquet")


def test_part_a_sql_invariants_on_sample(tmp_path):
    assert FIXTURE.exists(), "Sample fixture tests/fixtures/rees46_sample.parquet is missing."
    summary = run_part_a_sql([FIXTURE], sql_dir=Path("sql"), out_dir=tmp_path)

    # Funnel steps must never increase
    funnel_df = pd.read_parquet(tmp_path / "funnel_summary.parquet")
    assert (funnel_df["sessions_viewed"] >= funnel_df["sessions_carted"]).all()
    assert (funnel_df["sessions_carted"] >= funnel_df["sessions_purchased"]).all()
    assert (funnel_df["total_revenue"] >= 0).all()

    # Overall summary invariants
    assert summary["sessions_viewed"] >= summary["sessions_carted"] >= summary["sessions_purchased"]
    assert 0.0 <= summary["view_to_cart_rate"] <= 1.0
    assert 0.0 <= summary["cart_to_purchase_rate"] <= 1.0
    assert 0.0 <= summary["cart_abandonment_rate"] <= 1.0

    # Cohort sizes must add up and eligible subsets cannot exceed cohort_users
    cohorts_df = pd.read_parquet(tmp_path / "cohorts_weekly.parquet")
    assert len(cohorts_df) > 0
    assert int(cohorts_df["cohort_users"].sum()) == int(cohorts_df["total_eligible_cohort_users"].iloc[0])
    assert (cohorts_df["eligible_d7_users"] <= cohorts_df["cohort_users"]).all()
    assert (cohorts_df["returned_d7_users"] <= cohorts_df["eligible_d7_users"]).all()
    assert (cohorts_df["returned_d14_users"] <= cohorts_df["eligible_d14_users"]).all()
    assert (cohorts_df["returned_d28_users"] <= cohorts_df["eligible_d28_users"]).all()

    # Exact-day retention curve invariants
    curve_df = pd.read_parquet(tmp_path / "retention_curve.parquet")
    assert list(curve_df["day_n"]) == list(range(1, 29))
    assert (curve_df["retained_users"] <= curve_df["eligible_users"]).all()


def test_streamlit_app_imports_and_outputs_present():
    import app.streamlit_app as app_mod

    assert callable(app_mod.main)
    out_dir = Path("outputs")
    if (out_dir / "rees46_summary.json").exists():
        for name in [
            "rees46_summary.json",
            "data_quality.json",
            "funnel_summary.parquet",
            "cohorts_weekly.parquet",
            "retention_curve.parquet",
            "criteo_summary.json",
            "criteo_balance.parquet",
            "criteo_segments.parquet",
            "criteo_breakeven.parquet",
        ]:
            assert (out_dir / name).exists(), f"Missing {name}"

