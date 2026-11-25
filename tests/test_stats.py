"""Unit tests for Part B statistical functions."""

import numpy as np
import pytest

from src.stats import (
    benjamini_hochberg,
    build_breakeven_table,
    compute_mde_and_power,
    compute_smd,
    two_proportion_z_test,
)


def test_two_proportion_z_test_basic():
    res = two_proportion_z_test(conv_t=150, n_t=10000, conv_c=100, n_c=10000)
    assert res["rate_treat"] == pytest.approx(0.015)
    assert res["rate_ctrl"] == pytest.approx(0.010)
    assert res["abs_lift"] == pytest.approx(0.005)
    assert res["abs_lift_per_1000"] == pytest.approx(5.0)
    assert res["rel_lift"] == pytest.approx(0.5)
    assert res["incremental_conversions"] == pytest.approx(50.0)
    assert res["abs_lift_ci_low"] < res["abs_lift"] < res["abs_lift_ci_high"]
    assert res["rel_lift_ci_low"] < res["rel_lift"] < res["rel_lift_ci_high"]
    assert res["p_value"] < 0.01


def test_two_proportion_z_test_invalid_n():
    with pytest.raises(ValueError):
        two_proportion_z_test(conv_t=0, n_t=0, conv_c=10, n_c=100)


def test_compute_mde_and_power():
    res = compute_mde_and_power(
        p_baseline=0.02, n_treat=50000, n_ctrl=50000, observed_lift=0.005
    )
    assert res["mde_abs"] > 0
    assert res["mde_per_1000"] == pytest.approx(res["mde_abs"] * 1000.0)
    assert 0.9 <= res["achieved_power"] <= 1.0


def test_compute_smd():
    assert compute_smd(1.0, 4.0, 1.0, 4.0) == pytest.approx(0.0)
    assert compute_smd(2.0, 4.0, 0.0, 4.0) == pytest.approx(1.0)
    assert compute_smd(1.0, 0.0, 1.0, 0.0) == pytest.approx(0.0)


def test_benjamini_hochberg_monotone_and_bounded():
    p_vals = np.array([0.001, 0.02, 0.03, 0.50])
    adj = benjamini_hochberg(p_vals)
    assert np.all(adj >= p_vals)
    assert np.all(adj <= 1.0)
    assert adj[0] == pytest.approx(0.004)
    assert adj[1] == pytest.approx(0.04)
    assert adj[2] == pytest.approx(0.04)
    assert adj[3] == pytest.approx(0.50)


def test_build_breakeven_table():
    df = build_breakeven_table(
        abs_lift=0.001,
        abs_lift_ci_low=0.0008,
        abs_lift_ci_high=0.0012,
        values_per_conv=[1000.0],
        costs_per_user=[0.5, 2.0],
    )
    assert len(df) == 2
    assert df.iloc[0]["break_even_cost_per_user"] == pytest.approx(1.0)
    assert bool(df.iloc[0]["profitable"]) is True
    assert bool(df.iloc[1]["profitable"]) is False
