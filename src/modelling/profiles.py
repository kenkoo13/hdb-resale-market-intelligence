"""Pre-computed indicative estimates for defined flat profiles (BI page 5, DEC-026).

Why pre-computed
    Power BI Desktop cannot run the Python model when a slicer changes. Instead
    we estimate prices for an explicit, documented grid of *typical* profiles and
    publish them as a table, labelled as indicative, with the measured error for
    the profile's segment. The report never implies live inference.

Profile definition (per town x flat type with >= 30 sales in the latest 12 full months)
    * floor area           = median floor area of that segment's latest-12-month sales
    * lease commence year  = median (rounded) of the segment
    * remaining lease      = median of the segment
    * flat model           = most common model in the segment
    * street               = most common street in the segment (location within town)
    * storey               = three variants: low (01 TO 03), middle (07 TO 09), high (13 TO 15)
    * month                = last full month L (inside the data's coverage)

Model
    The selected configuration (DEC-024) refit on *all* full months up to L - the
    same procedure as the monthly-refit evaluation, whose test-year error is
    attached to each profile as its reliability context.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.modelling import models as M
from src.modelling.features import TARGET, build_features

MIN_SEGMENT_N = 30
STOREY_VARIANTS = {"Low floor (1-3)": ("01 TO 03", 2.0), "Middle floor (7-9)": ("07 TO 09", 8.0),
                   "High floor (13-15)": ("13 TO 15", 14.0)}
SELECTED_CONFIG = {"family": "G-B", "model": "hgb", "feature_set": "B",
                   "params": {"max_leaf_nodes": 31, "min_samples_leaf": 20}}


def build_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """Profile attribute grid from the latest 12 full months of ``df`` (analysis-ready + time index)."""
    last = df["month_date"].max()
    recent = df[df["month_date"] > last - pd.DateOffset(months=12)]
    rows = []
    for (town, ft), g in recent.groupby(["town", "flat_type"]):
        if len(g) < MIN_SEGMENT_N:
            continue
        base = {
            "town": town, "flat_type": ft, "segment_sales_latest_12m": len(g),
            "segment_median_price_latest_12m": float(g[TARGET].median()),
            "floor_area_sqm_num": float(g["floor_area_sqm_num"].median()),
            "lease_commence_year": float(round(g["lease_commence_year"].astype(float).median())),
            "remaining_lease_years": float(g["remaining_lease_years"].median()),
            "flat_model": g["flat_model"].mode().iloc[0],
            "street_name": g["street_name"].mode().iloc[0],
            "months_since_start": int(df["months_since_start"].max()),
            "month_date": last,
        }
        for label, (band, mid) in STOREY_VARIANTS.items():
            rows.append({**base, "storey_variant": label, "storey_range": band, "storey_mid": mid,
                         "storey_band_sales_in_segment": int((g["storey_range"] == band).sum())})
    return pd.DataFrame(rows)


def estimate_profiles(df: pd.DataFrame, seg_errors: pd.DataFrame) -> pd.DataFrame:
    """Fit the selected model on all of ``df`` and estimate every profile.

    ``seg_errors``: monthly-refit test segment errors (town, flat_type rows) used as
    the reliability context shown next to each estimate.
    """
    profiles = build_profiles(df)
    model = M.build(SELECTED_CONFIG)
    model.fit(build_features(df, "B"), df[TARGET])
    profiles["estimated_price"] = model.predict(build_features(profiles, "B"))
    profiles["estimated_price_rounded"] = (profiles["estimated_price"] / 1000).round() * 1000

    def lookup(segment: str, key: str) -> pd.Series:
        s = seg_errors[seg_errors["segment"] == segment].set_index("level")
        return profiles[key].map(s["mdape_pct"]), profiles[key].map(s["n"])

    profiles["town_test_mdape_pct"], profiles["town_test_n"] = lookup("town", "town")
    profiles["flat_type_test_mdape_pct"], profiles["flat_type_test_n"] = lookup("flat_type", "flat_type")
    profiles["typical_error_pct"] = profiles[["town_test_mdape_pct", "flat_type_test_mdape_pct"]].max(axis=1)
    profiles["typical_error_sgd"] = (profiles["estimated_price"] * profiles["typical_error_pct"] / 100).round(-2)
    profiles["estimate_vs_segment_median_pct"] = 100 * (
        profiles["estimated_price"] / profiles["segment_median_price_latest_12m"] - 1)
    profiles["reliability"] = np.select(
        [profiles["flat_type_test_n"].fillna(0) < MIN_SEGMENT_N,
         profiles["storey_band_sales_in_segment"] < 10],
        ["Lower: this flat type is rarely sold", "Lower: this floor level is rarely sold here"],
        default="Normal")
    profiles["estimate_month"] = profiles["month_date"].dt.strftime("%Y-%m")
    cols = ["town", "flat_type", "storey_variant", "storey_range", "flat_model", "street_name",
            "floor_area_sqm_num", "remaining_lease_years", "lease_commence_year", "estimate_month",
            "estimated_price", "estimated_price_rounded", "typical_error_pct", "typical_error_sgd",
            "reliability", "segment_sales_latest_12m", "segment_median_price_latest_12m",
            "storey_band_sales_in_segment", "estimate_vs_segment_median_pct",
            "town_test_mdape_pct", "flat_type_test_mdape_pct"]
    return profiles[cols].rename(columns={"floor_area_sqm_num": "floor_area_sqm"})
