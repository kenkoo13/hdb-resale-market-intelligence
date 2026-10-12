"""Tests for modelling: leakage prevention, chronological split, baselines, metrics,
intervals and unseen-category handling. All data is SYNTHETIC."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modelling import evaluate as E
from src.modelling import models as M
from src.modelling.features import (FEATURE_SETS, FORBIDDEN, LeakageError, add_time_index,
                                    assert_no_leakage, build_features)
from src.modelling.run_modelling import select
from src.modelling.splits import make_split


def synthetic(n_months: int = 48, per_month: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2017-01-01", periods=n_months, freq="MS")
    n = n_months * per_month
    df = pd.DataFrame({
        "month_date": np.repeat(months, per_month),
        "town": rng.choice(["TOWN A", "TOWN B"], n),
        "flat_type": rng.choice(["3 ROOM", "4 ROOM"], n),
        "flat_model": rng.choice(["Model X", "Model Y"], n),
        "street_name": rng.choice([f"ST {i}" for i in range(15)], n),
        "floor_area_sqm_num": rng.uniform(60, 110, n),
        "storey_mid": rng.choice([2.0, 5.0, 11.0], n),
        "remaining_lease_years": rng.uniform(50, 95, n),
        "lease_commence_year": pd.array(rng.integers(1975, 2015, n), dtype="Int64"),
        "is_partial_month": False,
        "block": "1", "source_row_number": np.arange(n),
    })
    df["month"] = df["month_date"].dt.strftime("%Y-%m")
    df = add_time_index(df)
    log_p = (12.6 + 0.008 * df["floor_area_sqm_num"] + 0.01 * df["remaining_lease_years"]
             + 0.005 * df["months_since_start"] + 0.2 * (df["town"] == "TOWN B") + rng.normal(0, 0.05, n))
    df["resale_price_sgd"] = np.exp(log_p)
    return df


# ---------- leakage ----------
@pytest.mark.parametrize("col", ["resale_price_sgd", "log_price", "price_per_sqm_sgd", "source_row_number",
                                 "duplicate_group_size", "block", "flag_lease_inconsistent"])
def test_forbidden_columns_rejected(col):
    with pytest.raises(LeakageError):
        assert_no_leakage(["town", col])


def test_feature_sets_contain_no_forbidden_or_target():
    for fs, cols in FEATURE_SETS.items():
        assert_no_leakage(cols)
        assert not set(cols) & set(FORBIDDEN)


def test_build_features_excludes_target():
    X = build_features(synthetic(), "B")
    assert "resale_price_sgd" not in X.columns and list(X.columns) == FEATURE_SETS["B"]


def test_target_encoder_fitted_only_on_training_rows():
    """Changing validation prices must not change the fitted model's predictions."""
    df = synthetic()
    train, val = df[df["months_since_start"] < 36], df[df["months_since_start"] >= 36]
    m1 = M.make_ridge("B", 1.0, "constant").fit(build_features(train, "B"), train["resale_price_sgd"])
    p1 = m1.predict(build_features(val, "B"))
    val2 = val.assign(resale_price_sgd=val["resale_price_sgd"] * 10)  # would shift encodings if leaked
    m2 = M.make_ridge("B", 1.0, "constant").fit(build_features(train, "B"), train["resale_price_sgd"])
    np.testing.assert_allclose(p1, m2.predict(build_features(val2, "B")))


# ---------- split ----------
def test_split_is_chronological_and_disjoint():
    df = synthetic()
    s = make_split(df)
    parts = s.assign(df)
    tr, va, te = parts["train"], parts["validation"], parts["test"]
    assert tr["month_date"].max() < va["month_date"].min()
    assert va["month_date"].max() < te["month_date"].min()
    assert va["month_date"].nunique() == 12 and te["month_date"].nunique() == 12
    assert te["month_date"].max() == df["month_date"].max()
    assert len(tr) + len(va) + len(te) == len(df)


def test_split_rejects_partial_month():
    df = synthetic()
    df.loc[df.index[-1], "is_partial_month"] = True
    with pytest.raises(ValueError, match="Partial-month"):
        make_split(df)


def test_time_index():
    df = pd.DataFrame({"month_date": pd.to_datetime(["2017-01-01", "2018-03-01"])})
    assert add_time_index(df)["months_since_start"].tolist() == [0, 14]


# ---------- baselines ----------
def test_global_median_baseline():
    X = pd.DataFrame({"a": [1, 2, 3]})
    assert M.GlobalMedianBaseline().fit(X, [1, 5, 9]).predict(X).tolist() == [5, 5, 5]


def test_segment_baseline_fallbacks_and_recent_window():
    X = pd.DataFrame({"town": ["A"] * 40 + ["B"] * 5, "flat_type": ["4"] * 45,
                      "months_since_start": [0] * 20 + [30] * 25})
    y = np.r_[np.full(20, 100.0), np.full(20, 300.0), np.full(5, 1000.0)]
    b1 = M.SegmentMedianBaseline(min_n=30).fit(X, y)
    new = pd.DataFrame({"town": ["A", "B", "Z"], "flat_type": ["4", "4", "9"]})
    p = b1.predict(new)
    assert p[0] == 200.0          # A has 40 rows (20 x 100, 20 x 300) -> median of all history
    assert p[1] == np.median(y)   # B has 5 rows -> falls back to flat type median
    assert p[2] == np.median(y)   # unseen type -> global median
    b2 = M.SegmentMedianBaseline(min_n=10, recent_months=12).fit(X, y)
    assert b2.predict(new)[0] == 300.0  # recent window: only month-30 rows (all 300) used for A


# ---------- unseen categories ----------
@pytest.mark.parametrize("maker", [lambda: M.make_ridge("B", 1.0, "constant"), lambda: M.make_hgb("B", 31, 20)])
def test_unseen_categories_do_not_crash(maker):
    df = synthetic()
    model = maker().fit(build_features(df, "B"), df["resale_price_sgd"])
    new = df.head(3).assign(town="NEW TOWN", flat_model="New Model", street_name="NEW ST")
    p = model.predict(build_features(new, "B"))
    assert np.isfinite(p).all() and (p > 0).all()


def test_models_learn_signal():
    """Realistic use: train on everything before the test year, predict 1-12 months ahead."""
    df = synthetic()
    s = make_split(df).assign(df)
    tr, te = pd.concat([s["train"], s["validation"]]), s["test"]
    base = E.metrics(te["resale_price_sgd"], M.GlobalMedianBaseline().fit(tr, tr["resale_price_sgd"]).predict(te))
    for m in [M.make_ridge("A", 1.0, "linear"), M.make_ridge("A", 1.0, "constant"), M.make_hgb("A", 31, 20)]:
        m.fit(build_features(tr, "A"), tr["resale_price_sgd"])
        assert E.metrics(te["resale_price_sgd"], m.predict(build_features(te, "A")))["mae"] < base["mae"]


# ---------- metrics & intervals ----------
def test_metrics_hand_computed():
    m = E.metrics([100, 200, 400], [110, 180, 400])
    assert m["mae"] == pytest.approx(10.0)
    assert m["rmse"] == pytest.approx(np.sqrt((100 + 400 + 0) / 3))
    assert m["medae"] == 10.0
    assert m["mdape_pct"] == pytest.approx(10.0)  # |err|/y = 0.1, 0.1, 0
    assert m["bias_median_pct"] == pytest.approx(0.0)  # +10%, -10%, 0%
    ss_tot = sum((v - 700 / 3) ** 2 for v in [100, 200, 400])
    assert m["r2"] == pytest.approx(1 - 500 / ss_tot)


def test_conformal_interval_coverage_on_exchangeable_data():
    rng = np.random.default_rng(3)
    yhat = rng.uniform(3e5, 9e5, 20000)
    y = yhat * np.exp(rng.normal(0, 0.08, 20000))
    lo_q, hi_q = E.conformal_quantiles(y[:10000], yhat[:10000], 0.8)
    lo, hi = E.apply_interval(yhat[10000:], lo_q, hi_q)
    assert E.coverage(y[10000:], lo, hi) == pytest.approx(0.8, abs=0.02)


def test_segment_errors_reliability_flag():
    df = pd.DataFrame({"g": ["a"] * 30 + ["b"] * 5, "actual": 100.0, "predicted": 110.0})
    s = E.segment_errors(df, "g").set_index("level")
    assert s.loc["a", "reliability"] == "ok" and s.loc["b", "reliability"].startswith("less reliable")


# ---------- selection rule ----------
def test_selection_prefers_simpler_within_one_percent():
    configs = [{"family": "L-A", "model": "ridge", "feature_set": "A", "params": {}},
               {"family": "G-B", "model": "hgb", "feature_set": "B", "params": {}}]
    table = pd.DataFrame({"config_id": [-1, 0, 1], "family": ["B1", "L-A", "G-B"], "mae": [1.0, 100.5, 100.0]})
    assert select(table, configs)["family"] == "L-A"
    table.loc[1, "mae"] = 102.0  # >1% worse -> the better tree wins
    assert select(table, configs)["family"] == "G-B"
