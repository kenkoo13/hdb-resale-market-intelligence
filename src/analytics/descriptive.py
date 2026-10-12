"""Descriptive market statistics (Q1 market overview, Q2 comparable properties).

Purpose
    Produces the robust descriptive tables behind the EDA figures and the Power BI
    report: monthly volume and price, distribution shape, segment comparisons
    with transaction counts, and the changing mix of flats sold.

Conventions
    * Medians (and quartiles) are the headline statistic: prices are right-skewed,
      so the mean is pulled up by a minority of expensive flats (see
      ``distribution_summary`` for the measured skew).
    * Every segment row carries ``transactions`` and ``low_sample`` (n < 30) so no
      comparison is shown without its sample size.
    * Inputs are analysis-ready rows (``common.analysis_ready``) unless stated;
      ``monthly_market`` also reports the partial month, flagged, for display.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from src.analytics.common import MIN_SEGMENT_N

FLOOR_AREA_BINS = [0, 50, 70, 90, 110, 130, 150, np.inf]
FLOOR_AREA_LABELS = ["<50", "50-69", "70-89", "90-109", "110-129", "130-149", "150+"]


def _q(p: float):
    def f(s: pd.Series) -> float:
        return float(s.quantile(p))
    f.__name__ = f"p{int(p * 100)}"
    return f


def segment_summary(df: pd.DataFrame, by: list[str] | str) -> pd.DataFrame:
    """Count, median, quartiles, mean and median price per sqm per segment."""
    by = [by] if isinstance(by, str) else by
    g = df.groupby(by, observed=True)
    out = g.agg(
        transactions=("resale_price_sgd", "size"),
        median_price=("resale_price_sgd", "median"),
        p25_price=("resale_price_sgd", _q(0.25)),
        p75_price=("resale_price_sgd", _q(0.75)),
        mean_price=("resale_price_sgd", "mean"),
        median_price_per_sqm=("price_per_sqm_sgd", "median"),
        median_floor_area_sqm=("floor_area_sqm_num", "median"),
        median_remaining_lease_years=("remaining_lease_years", "median"),
    ).reset_index()
    out["iqr_price"] = out["p75_price"] - out["p25_price"]
    out["low_sample"] = out["transactions"] < MIN_SEGMENT_N
    return out


def monthly_market(clean: pd.DataFrame) -> pd.DataFrame:
    """Monthly volume and price statistics; partial month included but flagged."""
    df = clean.assign(month=clean["month_date"].dt.strftime("%Y-%m"))
    out = segment_summary(df, "month")
    partial = df.groupby("month")["is_partial_month"].any()
    out["is_partial_month"] = out["month"].map(partial)
    return out


def add_bands(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["floor_area_band"] = pd.cut(out["floor_area_sqm_num"], FLOOR_AREA_BINS,
                                    labels=FLOOR_AREA_LABELS, right=False)
    return out


def distribution_summary(df: pd.DataFrame, label: str) -> dict:
    p = df["resale_price_sgd"]
    return {
        "population": label, "transactions": int(len(p)),
        "mean": float(p.mean()), "median": float(p.median()),
        "mean_minus_median": float(p.mean() - p.median()),
        "skewness": float(stats.skew(p)), "skewness_log_price": float(stats.skew(np.log(p))),
        "p10": float(p.quantile(.1)), "p90": float(p.quantile(.9)),
        "share_above_1m": float((p >= 1_000_000).mean()),
    }


def mix_over_time(df: pd.DataFrame) -> pd.DataFrame:
    """Composition of transactions by year: flat-type shares and typical attributes."""
    shares = (pd.crosstab(df["year"], df["flat_type"], normalize="index") * 100).add_prefix("share_pct_")
    attrs = df.groupby("year").agg(
        transactions=("resale_price_sgd", "size"),
        median_floor_area_sqm=("floor_area_sqm_num", "median"),
        median_remaining_lease_years=("remaining_lease_years", "median"),
        share_storey_mid_13_plus_pct=("storey_mid", lambda s: 100 * (s >= 13).mean()),
        median_price=("resale_price_sgd", "median"),
    )
    return attrs.join(shares).reset_index()


def thin_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Town x flat type cells in the given window, with low-sample flag."""
    cells = segment_summary(df, ["town", "flat_type"])
    return cells.sort_values(["low_sample", "transactions"], ascending=[False, True])
