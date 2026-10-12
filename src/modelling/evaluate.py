"""Evaluation metrics, segment error analysis and split-conformal intervals.

Formulas (docs/METRIC_DICTIONARY.md §4):
    MAE    = mean(|y - yhat|)                       SGD   (primary)
    RMSE   = sqrt(mean((y - yhat)^2))               SGD
    R2     = 1 - SS_res / SS_tot                    unitless
    MedAE  = median(|y - yhat|)                     SGD
    MdAPE  = median(|y - yhat| / y) * 100           %
    Bias   = median((yhat - y) / y) * 100           %  (+ = over-estimate)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_RELIABLE_N = 30


def metrics(y, yhat) -> dict[str, float]:
    y, yhat = np.asarray(y, dtype=float), np.asarray(yhat, dtype=float)
    err = yhat - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(y.size),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "medae": float(np.median(np.abs(err))),
        "mdape_pct": float(100 * np.median(np.abs(err) / y)),
        "bias_median_pct": float(100 * np.median(err / y)),
    }


def segment_errors(df: pd.DataFrame, by: str, y: str = "actual", yhat: str = "predicted") -> pd.DataFrame:
    rows = []
    for level, g in df.groupby(by, observed=True):
        m = metrics(g[y], g[yhat])
        rows.append({"segment": by, "level": str(level), **m,
                     "median_actual": float(g[y].median()),
                     "reliability": "ok" if m["n"] >= MIN_RELIABLE_N else "less reliable (n<30)"})
    return pd.DataFrame(rows)


def conformal_quantiles(y_cal, yhat_cal, coverage: float = 0.8) -> tuple[float, float]:
    """Empirical lower/upper quantiles of log residuals log(y) - log(yhat) on calibration data."""
    r = np.log(np.asarray(y_cal, float)) - np.log(np.asarray(yhat_cal, float))
    a = (1 - coverage) / 2
    return float(np.quantile(r, a)), float(np.quantile(r, 1 - a))


def apply_interval(yhat, q_lo: float, q_hi: float) -> tuple[np.ndarray, np.ndarray]:
    yhat = np.asarray(yhat, float)
    return yhat * np.exp(q_lo), yhat * np.exp(q_hi)


def coverage(y, lo, hi) -> float:
    y = np.asarray(y, float)
    return float(np.mean((y >= lo) & (y <= hi)))
