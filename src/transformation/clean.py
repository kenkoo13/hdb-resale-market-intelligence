"""Turn a raw snapshot into typed, cleaned, flagged transactions plus a quarantine.

Purpose
    Implements the cleaning rules in docs/DATA_QUALITY.md §3. Each rule is applied
    in a vectorised step and its affected-row count is returned so the data-quality
    report can state exactly what changed.

Inputs
    ``raw``: DataFrame of the 11 source columns as strings (read with
    ``dtype=str, keep_default_na=False``). ``retrieved_local``: snapshot retrieval
    timestamp in Singapore time (defines the partial-month flag, DEC-008).

Outputs (:class:`CleanResult`)
    * ``clean``       - one row per retained source row, original (normalised) text
                        columns + parsed/derived columns + flags. Grain: one
                        registered resale transaction as published.
    * ``quarantine``  - rows that cannot be safely interpreted, with their original
                        unmodified text and a ``quarantine_reasons`` code list.
    * ``rule_counts`` - {rule_id: affected_rows}.

Quarantine vs flag policy (DEC-010)
    A row is *quarantined* only when a field needed for every core analysis is
    missing or unparseable: month, town, flat_type, storey_range, floor_area_sqm,
    resale_price, or the month is outside coverage. Problems in secondary fields
    (block, street_name, flat_model, lease fields) null that field and set a flag;
    the row is kept because it is still valid for price/volume analysis.
    Unusual-but-valid values (very large flats, very high prices, rare categories)
    are *never* removed here; they get warning flags for analysis-time decisions.

Duplicates (DEC-013, supersedes DEC-009)
    Rows identical on all 11 normalised source fields are kept and annotated with
    ``duplicate_group_size`` (1 = unique), *except* the evidenced 2017 artefact:
    later copies of exact-duplicate rows registered in 2017 at exactly SGD 468,000
    or 470,000 are moved to the exception report (reason Q07). The first copy stays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.transformation import parsers as P
from src.validation.schema import EXPECTED_COLUMNS

COVERAGE_START = pd.Timestamp("2017-01-01")  # dataset title: "from Jan-2017 onwards"
STANDARD_LEASE_YEARS = 99  # HDB flats are sold on 99-year leases

# Category reference sets observed in the 2026-10-12 snapshot. Values outside these
# sets are *kept* and flagged (is_new_category) so a refresh that introduces, e.g.,
# a new town is surfaced in the DQ report rather than silently dropped.
KNOWN_TOWNS = frozenset({
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG",
    "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS",
    "PUNGGOL", "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
})
KNOWN_FLAT_TYPES = frozenset({
    "1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE", "MULTI-GENERATION",
})
FLAT_TYPE_ORDER = ["1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE", "MULTI-GENERATION"]

# Plausibility bounds: wide enough that every legitimate HDB flat falls inside,
# narrow enough to catch unit/scale errors (e.g. price in thousands, area in sq ft).
# Rows outside are FLAGGED, not removed. Rationale: DEC-011.
FLOOR_AREA_PLAUSIBLE = (20.0, 400.0)       # sqm
PRICE_PLAUSIBLE = (50_000.0, 3_000_000.0)  # SGD
LEASE_DISCREPANCY_TOLERANCE_YEARS = 1.5    # see DEC-012

# Suspected publication artefact (DEC-013): evidence in docs/DATA_QUALITY.md §4.
ARTEFACT_YEAR = 2017
ARTEFACT_PRICES = (468_000.0, 470_000.0)

REQUIRED_FIELDS = ["month", "town", "flat_type", "storey_range", "floor_area_sqm", "resale_price"]


@dataclass
class CleanResult:
    clean: pd.DataFrame
    quarantine: pd.DataFrame
    rule_counts: dict[str, int] = field(default_factory=dict)
    new_categories: dict[str, list[str]] = field(default_factory=dict)


def clean_snapshot(raw: pd.DataFrame, retrieved_local: datetime) -> CleanResult:
    counts: dict[str, int] = {}
    original = raw[EXPECTED_COLUMNS].copy()
    original.insert(0, "source_row_number", np.arange(1, len(original) + 1))
    df = original.copy()

    # R01 whitespace normalisation (all text fields)
    for col in EXPECTED_COLUMNS:
        normed = P.normalise_text(df[col].fillna(""))
        counts[f"R01_whitespace_normalised:{col}"] = int((normed != df[col].fillna("")).sum())
        df[col] = normed

    # R02 case normalisation for upper-case code lists
    for col in ["town", "flat_type", "street_name", "storey_range"]:
        upper = df[col].str.upper()
        counts[f"R02_uppercased:{col}"] = int((upper != df[col]).sum())
        df[col] = upper

    # R03 flat_model: canonical label per case-insensitive group (most frequent spelling)
    lower = df["flat_model"].str.lower()
    canonical = (df.assign(_k=lower).groupby("_k")["flat_model"]
                 .agg(lambda s: s.value_counts().idxmax()))
    fm = lower.map(canonical).fillna(df["flat_model"])
    counts["R03_flat_model_case_unified"] = int((fm != df["flat_model"]).sum())
    df["flat_model"] = fm

    # Parsing
    month_date = P.parse_month(df["month"])
    floor_area = P.parse_decimal(df["floor_area_sqm"])
    price = P.parse_decimal(df["resale_price"])
    storey = P.parse_storey_range(df["storey_range"])
    lease_year = P.parse_year(df["lease_commence_date"])
    lease = P.parse_remaining_lease(df["remaining_lease"])

    retrieval_month = pd.Timestamp(retrieved_local.year, retrieved_local.month, 1)

    # Quarantine reasons
    reasons: dict[str, pd.Series] = {}
    for col in REQUIRED_FIELDS:
        reasons[f"Q01_missing_{col}"] = P.is_blank(df[col])
    blank = {c: reasons[f"Q01_missing_{c}"] for c in REQUIRED_FIELDS}
    reasons["Q02_invalid_month_format"] = month_date.isna() & ~blank["month"]
    reasons["Q03_month_outside_coverage"] = month_date.notna() & (
        (month_date < COVERAGE_START) | (month_date > retrieval_month))
    reasons["Q04_invalid_resale_price"] = ~blank["resale_price"] & (price.isna() | (price <= 0))
    reasons["Q05_invalid_floor_area"] = ~blank["floor_area_sqm"] & (floor_area.isna() | (floor_area <= 0))
    reasons["Q06_invalid_storey_range"] = ~blank["storey_range"] & storey["storey_lower"].isna()

    reason_frame = pd.DataFrame(reasons)
    for k, v in reasons.items():
        counts[k] = int(v.sum())
    is_quarantined = reason_frame.any(axis=1)
    codes = reason_frame.columns.to_numpy()
    reason_text = reason_frame.apply(lambda r: ";".join(codes[r.to_numpy()]), axis=1) \
        if is_quarantined.any() else pd.Series("", index=df.index)

    quarantine = original.loc[is_quarantined].copy()
    quarantine["quarantine_reasons"] = reason_text[is_quarantined].values

    # Build the clean table (non-quarantined rows only)
    keep = ~is_quarantined
    out = df.loc[keep, ["source_row_number", *EXPECTED_COLUMNS]].copy()
    out["month_date"] = month_date[keep]
    out["year"] = out["month_date"].dt.year.astype("Int64")
    out["floor_area_sqm_num"] = floor_area[keep]
    out["resale_price_sgd"] = price[keep]
    out = out.join(storey.loc[keep])
    out["lease_commence_year"] = lease_year[keep]
    out = out.join(lease.loc[keep])

    # Secondary-field flags (row kept, value nulled by the parser)
    # A lease cannot start after the resale is registered; such a year is unusable.
    future_lease = (out["lease_commence_year"] > out["year"]).fillna(False).astype(bool)
    out["flag_invalid_lease_commence"] = out["lease_commence_year"].isna().to_numpy() | future_lease
    out.loc[future_lease, "lease_commence_year"] = pd.NA
    out["flag_invalid_remaining_lease"] = out["remaining_lease_months"].isna()
    for col in ["block", "street_name", "flat_model"]:
        out[f"flag_missing_{col}"] = out[col] == ""
        out.loc[out[col] == "", col] = pd.NA

    # Derived fields (formulas: docs/METRIC_DICTIONARY.md)
    out["price_per_sqm_sgd"] = out["resale_price_sgd"] / out["floor_area_sqm_num"]
    # Approximate remaining lease implied by the lease start year. Lease start month is
    # unknown, so the start is assumed to be 1 Jan of lease_commence_year; this
    # over-states elapsed time by up to ~1 year. Used only as a consistency check (DEC-012).
    elapsed = (out["year"] - out["lease_commence_year"]).astype("float64") + \
        (out["month_date"].dt.month - 1) / 12.0
    out["derived_remaining_lease_years"] = STANDARD_LEASE_YEARS - elapsed
    out["lease_discrepancy_years"] = out["remaining_lease_years"] - out["derived_remaining_lease_years"]
    out["flag_lease_inconsistent"] = out["lease_discrepancy_years"].abs() > LEASE_DISCREPANCY_TOLERANCE_YEARS

    # Plausibility warnings (kept)
    lo, hi = FLOOR_AREA_PLAUSIBLE
    out["flag_implausible_floor_area"] = ~out["floor_area_sqm_num"].between(lo, hi)
    lo, hi = PRICE_PLAUSIBLE
    out["flag_implausible_price"] = ~out["resale_price_sgd"].between(lo, hi)

    # New categories (kept, surfaced)
    new_categories = {
        "town": sorted(set(out["town"]) - KNOWN_TOWNS),
        "flat_type": sorted(set(out["flat_type"]) - KNOWN_FLAT_TYPES),
    }
    out["flag_new_category"] = ~out["town"].isin(KNOWN_TOWNS) | ~out["flat_type"].isin(KNOWN_FLAT_TYPES)

    # Partial month (DEC-008)
    out["is_partial_month"] = out["month_date"] >= retrieval_month

    # Duplicates (DEC-013, supersedes DEC-009). Exact duplicates are generally kept as
    # plausible separate sales. The exception is the pattern evidenced in DATA_QUALITY.md
    # §4: in 2017, extra copies of rows priced exactly at ARTEFACT_PRICES. Those excess
    # copies (every copy after the first by source order) move to the exception report.
    dup_key = out.groupby(EXPECTED_COLUMNS, dropna=False, sort=False).ngroup()
    is_later_copy = dup_key.duplicated(keep="first")
    artefact = (is_later_copy & (out["year"] == ARTEFACT_YEAR).to_numpy()
                & out["resale_price_sgd"].isin(ARTEFACT_PRICES).to_numpy())
    counts["Q07_suspected_duplicate_artefact"] = int(artefact.sum())
    if artefact.any():
        extra = original.loc[artefact[artefact].index].copy()
        extra["quarantine_reasons"] = "Q07_suspected_duplicate_artefact"
        quarantine = pd.concat([quarantine, extra])
        out = out.loc[~artefact]
    out["duplicate_group_size"] = out.groupby(EXPECTED_COLUMNS, dropna=False)["source_row_number"] \
        .transform("size").astype("int64")

    for col in [c for c in out.columns if c.startswith("flag_")] + ["is_partial_month"]:
        counts[f"F_{col}"] = int(out[col].sum())
    counts["F_rows_in_retained_duplicate_groups"] = int((out["duplicate_group_size"] > 1).sum())
    counts["F_retained_excess_duplicate_rows"] = int(out.duplicated(EXPECTED_COLUMNS).sum())

    return CleanResult(clean=out.reset_index(drop=True),
                       quarantine=quarantine.sort_values("source_row_number").reset_index(drop=True),
                       rule_counts=counts, new_categories=new_categories)
