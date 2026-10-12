"""Tests for the analysis layer (descriptive stats, hedonic model, hypothesis rules).

All data here is SYNTHETIC, generated with known parameters so the tests can
check that the methods recover the truth - not merely that the code runs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from src.analytics import descriptive as D
from src.analytics import hedonic as H
from src.analytics import hypotheses as HY

TRUE_STOREY = 0.007   # log-points per floor  -> +10 floors = +7.25%
TRUE_LEASE = 0.010    # per year
TRUE_AREA = 0.008     # per sqm
TRUE_MONTH_STEP = 0.01  # market rises 1% per month


@pytest.fixture(scope="module")
def synthetic_market() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 6000
    months = [f"2020-{m:02d}" for m in range(1, 13)]
    df = pd.DataFrame({
        "month": rng.choice(months, n),
        "town": rng.choice(["TOWN A", "TOWN B", "TOWN C"], n),
        "flat_type": rng.choice(["3 ROOM", "4 ROOM"], n),
        "flat_model": rng.choice(["Model X", "Model Y"], n),
        "storey_mid": rng.choice([2, 5, 8, 11, 14, 20, 30], n).astype(float),
        "remaining_lease_years": rng.uniform(50, 95, n),
        "building": rng.integers(0, 400, n).astype(str),
    })
    df["floor_area_sqm_num"] = np.where(df["flat_type"] == "4 ROOM", 92, 67) + rng.normal(0, 5, n)
    month_idx = df["month"].str[-2:].astype(int) - 1
    town_eff = df["town"].map({"TOWN A": 0.0, "TOWN B": 0.2, "TOWN C": -0.1})
    building_eff = pd.Series(rng.normal(0, 0.05, 400)).astype(float)[df["building"].astype(int)].to_numpy()
    df["log_price"] = (12.5 + TRUE_MONTH_STEP * month_idx + town_eff + 0.1 * (df["flat_type"] == "4 ROOM")
                       + TRUE_STOREY * df["storey_mid"] + TRUE_LEASE * df["remaining_lease_years"]
                       + TRUE_AREA * df["floor_area_sqm_num"] + building_eff + rng.normal(0, 0.05, n))
    df["resale_price_sgd"] = np.exp(df["log_price"])
    df["price_per_sqm_sgd"] = df["resale_price_sgd"] / df["floor_area_sqm_num"]
    return df


@pytest.fixture(scope="module")
def m1(synthetic_market):
    return H.fit(synthetic_market, H.M1_FORMULA)


@pytest.mark.parametrize("term,truth", [("storey_mid", TRUE_STOREY), ("remaining_lease_years", TRUE_LEASE),
                                        ("floor_area_sqm_num", TRUE_AREA)])
def test_hedonic_recovers_known_coefficients(m1, term, truth):
    lo, hi = m1.conf_int().loc[term]
    assert lo <= truth <= hi, f"{term}: true {truth} outside CI [{lo:.5f}, {hi:.5f}]"


def test_pct_effect_conversion(m1):
    e = H.pct_effect(m1, "storey_mid", 10)
    assert e["pct"] == pytest.approx(100 * np.expm1(m1.params["storey_mid"] * 10))
    assert e["pct_ci_low"] < e["pct"] < e["pct_ci_high"]
    assert 0 <= e["p_one_sided_positive"] < 0.001


def test_month_index_recovers_market_trend(m1, synthetic_market):
    months = sorted(synthetic_market["month"].unique())
    idx = H.month_index(m1, months)
    assert idx["index"].iloc[0] == 1.0
    assert idx["log_index"].iloc[-1] == pytest.approx(TRUE_MONTH_STEP * 11, abs=0.01)


def test_period_change_matches_definition_and_truth(m1, synthetic_market):
    months = sorted(synthetic_market["month"].unique())
    base, comp = months[:3], months[-3:]
    res = H.period_change(m1, months, base, comp)
    idx = H.month_index(m1, months).set_index("month")["index"]
    assert res["ratio"] == pytest.approx(idx[comp].mean() / idx[base].mean())
    true_ratio = np.mean(np.exp(TRUE_MONTH_STEP * np.arange(9, 12))) / np.mean(np.exp(TRUE_MONTH_STEP * np.arange(3)))
    assert res["pct_ci_low"] <= 100 * (true_ratio - 1) <= res["pct_ci_high"]


def test_categorical_effects_reference_and_values(m1):
    towns = H.categorical_effects(m1, "town").set_index("level")
    assert set(towns.index) == {"TOWN B", "TOWN C"}  # TOWN A is the reference
    assert towns.loc["TOWN B", "pct_vs_reference"] == pytest.approx(100 * np.expm1(0.2), abs=3)


def test_segment_summary_values_and_low_sample_flag():
    df = pd.DataFrame({"g": ["a"] * 31 + ["b"] * 3, "resale_price_sgd": list(range(1, 32)) + [10, 20, 90],
                       "price_per_sqm_sgd": 1.0, "floor_area_sqm_num": 1.0, "remaining_lease_years": 1.0})
    s = D.segment_summary(df, "g").set_index("g")
    assert s.loc["a", "transactions"] == 31 and s.loc["a", "median_price"] == 16
    assert s.loc["b", "median_price"] == 20 and s.loc["b", "mean_price"] == 40
    assert s.loc["a", "p25_price"] == pytest.approx(8.5)
    assert not s.loc["a", "low_sample"] and s.loc["b", "low_sample"]


def test_epsilon_squared_formula():
    rng = np.random.default_rng(1)
    groups = [rng.normal(0, 1, 50), rng.normal(0.5, 1, 50), rng.normal(1, 1, 50)]
    h, _ = stats.kruskal(*groups)
    eps2 = h / (150 - 1)
    assert 0 < eps2 < 1
    same = [rng.normal(0, 1, 50) for _ in range(3)]
    assert stats.kruskal(*same)[0] / 149 < eps2


@pytest.mark.parametrize("p,pct,lo,hi,expected", [
    (0.001, 7.8, 7.5, 8.0, "Supported"),
    (0.20, 7.8, -1.0, 15.0, "Not supported"),
    (0.001, -3.0, -4.0, -2.0, "Not supported"),
    (0.001, 1.0, 0.5, 1.5, "Not supported (association real but below practical threshold)"),
    (0.001, 2.5, 1.5, 3.5, "Inconclusive (significant, but CI spans practical threshold)"),
])
def test_decision_rule_matches_register(p, pct, lo, hi, expected):
    assert HY._decide_coef(p, pct, lo, hi) == expected


def test_lease_bands():
    df = pd.DataFrame({"remaining_lease_years": [44.99, 45.0, 97.75]})
    assert H.add_lease_band(df)["lease_band"].tolist() == ["40-44", "45-49", "95-99"]


def test_floor_area_bands_left_closed():
    df = pd.DataFrame({"floor_area_sqm_num": [49.9, 50.0, 150.0]})
    assert D.add_bands(df)["floor_area_band"].astype(str).tolist() == ["<50", "50-69", "150+"]
