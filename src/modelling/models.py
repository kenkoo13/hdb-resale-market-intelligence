"""Baselines and candidate model pipelines (docs/MODEL_CARD.md §4).

Every estimator here takes ``(X, y_price)`` in ``fit`` and returns predicted
prices in SGD from ``predict``. Log-target models are wrapped in
``TransformedTargetRegressor(func=np.log, inverse_func=np.exp)`` so callers
never handle the log scale. All preprocessing (encoding, splines, scaling,
target encoding, imputation) lives *inside* each pipeline, so it is fitted only
on the rows passed to ``fit`` - the core leakage control for transformations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import (OneHotEncoder, OrdinalEncoder, SplineTransformer, StandardScaler,
                                   TargetEncoder)

from src.modelling.features import CATEGORICAL_A, STREET

SEED = 42


class GlobalMedianBaseline(RegressorMixin, BaseEstimator):
    """B0: predicts the training-set median price for every row."""

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.median_ = float(np.median(y))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.median_)


class SegmentMedianBaseline(RegressorMixin, BaseEstimator):
    """B1: median price by town x flat type; falls back to flat type, then global.

    A segment is used only if it has at least ``min_n`` training rows.
    ``recent_months`` (B2) restricts the medians to the last N months of the
    training data (by ``months_since_start``); None (B1) uses all training rows.
    """

    def __init__(self, min_n: int = 30, recent_months: int | None = None):
        self.min_n = min_n
        self.recent_months = recent_months

    def fit(self, X: pd.DataFrame, y: pd.Series):
        d = X[["town", "flat_type", "months_since_start"]].assign(y=np.asarray(y))
        if self.recent_months:
            d = d[d["months_since_start"] > d["months_since_start"].max() - self.recent_months]
        tf = d.groupby(["town", "flat_type"])["y"].agg(["median", "size"])
        self.town_type_ = tf.loc[tf["size"] >= self.min_n, "median"].to_dict()
        ft = d.groupby("flat_type")["y"].agg(["median", "size"])
        self.type_ = ft.loc[ft["size"] >= self.min_n, "median"].to_dict()
        self.global_ = float(np.median(d["y"]))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        keys = list(zip(X["town"], X["flat_type"]))
        out = pd.Series([self.town_type_.get(k) for k in keys], index=X.index, dtype="float64")
        out = out.fillna(X["flat_type"].map(self.type_)).fillna(self.global_)
        return out.to_numpy()


def _te_cv() -> KFold:
    """Shuffled, seeded 5-fold cross-fitting for TargetEncoder (no row sees its own price)."""
    return KFold(n_splits=5, shuffle=True, random_state=SEED)


def _log_target(model) -> TransformedTargetRegressor:
    return TransformedTargetRegressor(regressor=model, func=np.log, inverse_func=np.exp)


def make_ridge(feature_set: str, alpha: float, time_extrapolation: str) -> TransformedTargetRegressor:
    """Ridge on log price.

    * categoricals: one-hot (unknown levels -> all zeros, i.e. the average effect)
    * remaining lease: cubic spline, 8 knots (captures the non-linear lease curve)
    * time index: cubic spline, 12 knots; ``time_extrapolation`` controls behaviour
      beyond the training range: 'constant' holds the last level flat, 'linear'
      continues the final slope. Chosen on validation (DEC-020).
    * other numerics: median-imputed and standardised
    * street (set B): TargetEncoder with internal 5-fold cross-fitting, standardised
    """
    transformers: list[tuple[str, Any, list[str]]] = [
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5), CATEGORICAL_A),
        ("lease", make_pipeline(SimpleImputer(strategy="median"),
                                SplineTransformer(n_knots=8, degree=3, extrapolation="linear")),
         ["remaining_lease_years"]),
        ("time", SplineTransformer(n_knots=12, degree=3, extrapolation=time_extrapolation),
         ["months_since_start"]),
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()),
         ["floor_area_sqm_num", "storey_mid", "lease_commence_year"]),
    ]
    if feature_set == "B":
        transformers.append(("street", make_pipeline(
            TargetEncoder(target_type="continuous", cv=_te_cv()), StandardScaler()),
            [STREET]))
    pre = ColumnTransformer(transformers, remainder="drop")
    return _log_target(Pipeline([("pre", pre), ("model", Ridge(alpha=alpha))]))


def make_hgb(feature_set: str, max_leaf_nodes: int, min_samples_leaf: int) -> TransformedTargetRegressor:
    """HistGradientBoosting on log price with native categorical handling.

    Categoricals are ordinal-encoded (unknown -> NaN, treated as missing by HGB).
    Street (set B) is target-encoded with internal cross-fitting. Early stopping
    uses a random 10% of the *training* rows only.
    """
    cats = list(CATEGORICAL_A)
    transformers: list[tuple[str, Any, list[str]]] = [
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                               encoded_missing_value=np.nan), cats),
        ("num", "passthrough", ["floor_area_sqm_num", "storey_mid", "remaining_lease_years",
                                "lease_commence_year", "months_since_start"]),
    ]
    if feature_set == "B":
        transformers.append(("street", TargetEncoder(target_type="continuous", cv=_te_cv()), [STREET]))
    pre = ColumnTransformer(transformers, remainder="drop")
    n_out = len(cats) + 5 + (1 if feature_set == "B" else 0)
    cat_mask = [True] * len(cats) + [False] * (n_out - len(cats))
    hgb = HistGradientBoostingRegressor(
        learning_rate=0.1, max_iter=1000, max_leaf_nodes=max_leaf_nodes, min_samples_leaf=min_samples_leaf,
        categorical_features=cat_mask, early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=20, random_state=SEED)
    return _log_target(Pipeline([("pre", pre), ("model", hgb)]))


def candidate_grid() -> list[dict[str, Any]]:
    """All configurations evaluated on validation (MODEL_CARD §4, plus DEC-020 addition)."""
    grid: list[dict[str, Any]] = []
    for fs in ["A", "B"]:
        for alpha in [0.1, 1.0, 10.0]:
            for extrap in ["constant", "linear"]:
                grid.append({"family": f"L-{fs}", "model": "ridge", "feature_set": fs,
                             "params": {"alpha": alpha, "time_extrapolation": extrap}})
        for leaves in [31, 127]:
            for msl in [20, 100]:
                grid.append({"family": f"G-{fs}", "model": "hgb", "feature_set": fs,
                             "params": {"max_leaf_nodes": leaves, "min_samples_leaf": msl}})
    return grid


def build(config: dict[str, Any]):
    if config["model"] == "ridge":
        return make_ridge(config["feature_set"], **config["params"])
    if config["model"] == "hgb":
        return make_hgb(config["feature_set"], **config["params"])
    raise ValueError(config["model"])


def complexity_rank(config: dict[str, Any]) -> tuple[int, int]:
    """Lower = simpler: linear before tree, feature set A before B (selection tie-break)."""
    return (0 if config["model"] == "ridge" else 1, 0 if config["feature_set"] == "A" else 1)
