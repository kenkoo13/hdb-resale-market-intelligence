"""Model feature definitions and leakage guard (docs/MODEL_CARD.md §4-5).

Every feature listed here is observable before the transaction is registered.
``FORBIDDEN`` lists columns that must never reach a model, with the reason;
``build_features`` raises ``LeakageError`` if any of them is requested.
"""
from __future__ import annotations

import pandas as pd

TARGET = "resale_price_sgd"
TIME_ORIGIN = pd.Timestamp("2017-01-01")

CATEGORICAL_A = ["town", "flat_type", "flat_model"]
NUMERIC_A = ["floor_area_sqm_num", "storey_mid", "remaining_lease_years", "lease_commence_year",
             "months_since_start"]
STREET = "street_name"

FEATURE_SETS: dict[str, list[str]] = {
    "A": CATEGORICAL_A + NUMERIC_A,
    "B": CATEGORICAL_A + NUMERIC_A + [STREET],
}

FORBIDDEN: dict[str, str] = {
    "resale_price": "target (raw text)",
    "resale_price_sgd": "target",
    "log_price": "transformation of the target",
    "price_per_sqm_sgd": "target divided by floor area",
    "duplicate_group_size": "computed over all source fields including price",
    "source_row_number": "source file is largely price-ordered within month/town/type",
    "block": "near-unique identifier; excluded by design (location-level estimator)",
    "building": "near-unique identifier derived from block",
    "lease_discrepancy_years": "data-quality diagnostic, not a property attribute",
    "derived_remaining_lease_years": "data-quality diagnostic",
}


class LeakageError(ValueError):
    """Raised when a forbidden column is requested as a model feature."""


def assert_no_leakage(columns: list[str]) -> None:
    bad = sorted({c for c in columns if c in FORBIDDEN or c.startswith("flag_")})
    if bad:
        raise LeakageError(f"Forbidden feature(s): {bad} -> " +
                           "; ".join(f"{c}: {FORBIDDEN.get(c, 'data-quality flag')}" for c in bad))


def add_time_index(df: pd.DataFrame) -> pd.DataFrame:
    """months_since_start = whole months between 2017-01 and the transaction month."""
    out = df.copy()
    md = out["month_date"]
    out["months_since_start"] = (md.dt.year - TIME_ORIGIN.year) * 12 + (md.dt.month - TIME_ORIGIN.month)
    return out


def build_features(df: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    cols = FEATURE_SETS[feature_set]
    assert_no_leakage(cols)
    X = df[cols].copy()
    X["lease_commence_year"] = X["lease_commence_year"].astype("float64")
    for c in CATEGORICAL_A + ([STREET] if STREET in cols else []):
        X[c] = X[c].astype("object")
    return X
