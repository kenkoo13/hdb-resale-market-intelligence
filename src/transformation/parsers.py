"""Strict, vectorised parsers for source text fields.

Every parser takes a pandas ``Series`` of *strings* (the CSV is read with
``dtype=str, keep_default_na=False`` so nothing is coerced on read) and returns
parsed values with ``NaN``/``NaT``/``<NA>`` where the input is blank or does not
match the documented format. Parsers never guess: a value that does not match the
pattern is treated as invalid and handled by the cleaning rules
(``src/transformation/clean.py``). Formats are documented in docs/DATA_DICTIONARY.md.

Why strict regexes rather than ``pd.to_numeric(errors="coerce")`` alone
    ``to_numeric`` accepts forms such as ``"1e5"``, ``" inf"`` or ``"-0"`` that are
    not legitimate values for these fields. Matching an explicit pattern makes
    "what counts as valid" testable and documentable.
"""
from __future__ import annotations

import pandas as pd

MONTH_RE = r"^(\d{4})-(0[1-9]|1[0-2])$"
YEAR_RE = r"^\d{4}$"
DECIMAL_RE = r"^\d+(\.\d+)?$"
STOREY_RE = r"^(\d{2}) TO (\d{2})$"
# Observed formats (2026-10-12): "61 years 04 months", "63 years", "62 years 01 month".
LEASE_RE = r"^(\d{1,2}) years?(?: (\d{1,2}) months?)?$"


def parse_month(s: pd.Series) -> pd.Series:
    """'YYYY-MM' -> Timestamp at the first day of that month; invalid -> NaT."""
    valid = s.str.match(MONTH_RE)
    out = pd.to_datetime(s.where(valid) + "-01", format="%Y-%m-%d", errors="coerce")
    return out


def parse_decimal(s: pd.Series) -> pd.Series:
    """Unsigned plain decimal ('93', '366.7') -> float; anything else -> NaN.

    Thousands separators, signs, exponents and currency symbols are rejected on
    purpose: none appear in the source and their appearance would signal a
    format change that should be investigated, not silently absorbed.
    """
    valid = s.str.match(DECIMAL_RE)
    return pd.to_numeric(s.where(valid), errors="coerce").astype("float64")


def parse_year(s: pd.Series) -> pd.Series:
    """Four-digit year -> nullable Int64; invalid -> <NA>."""
    valid = s.str.match(YEAR_RE)
    return pd.to_numeric(s.where(valid), errors="coerce").astype("Int64")


def parse_storey_range(s: pd.Series) -> pd.DataFrame:
    """'10 TO 12' -> storey_lower=10, storey_upper=12, storey_mid=11.

    Ranges with lower > upper or lower < 1 are treated as invalid (all NaN).
    ``storey_mid`` is the arithmetic midpoint, an approximation of the unit's
    floor used for ordering and numeric modelling; the exact floor is unknown.
    """
    parts = s.str.extract(STOREY_RE)
    lower = pd.to_numeric(parts[0], errors="coerce")
    upper = pd.to_numeric(parts[1], errors="coerce")
    bad = (lower > upper) | (lower < 1)
    lower, upper = lower.mask(bad), upper.mask(bad)
    return pd.DataFrame({
        "storey_lower": lower.astype("Int64"),
        "storey_upper": upper.astype("Int64"),
        "storey_mid": (lower + upper) / 2.0,
    }, index=s.index)


def parse_remaining_lease(s: pd.Series) -> pd.DataFrame:
    """'61 years 04 months' -> remaining_lease_months=736, remaining_lease_years=61.333.

    'N years' (no month component) is read as N years 0 months. Months must be
    0-11; anything else is invalid. Returns NaN/<NA> for blanks and non-matching text.
    """
    parts = s.str.extract(LEASE_RE)
    years = pd.to_numeric(parts[0], errors="coerce")
    months = pd.to_numeric(parts[1], errors="coerce")
    has_years = years.notna()
    months = months.where(months.notna() | ~has_years, 0)  # "63 years" -> 0 months
    bad = months > 11
    total = (years * 12 + months).mask(bad)
    return pd.DataFrame({
        "remaining_lease_months": total.astype("Int64"),
        "remaining_lease_years": (total / 12.0).astype("float64"),
    }, index=s.index)


def normalise_text(s: pd.Series) -> pd.Series:
    """Trim and collapse internal whitespace; preserves case."""
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def is_blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.str.strip() == "")


__all__ = [
    "parse_month", "parse_decimal", "parse_year", "parse_storey_range",
    "parse_remaining_lease", "normalise_text", "is_blank",
]
