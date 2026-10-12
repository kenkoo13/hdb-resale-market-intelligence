"""Unit tests for strict field parsers (src/transformation/parsers.py)."""
import pandas as pd
import pytest

from src.transformation import parsers as P


def s(*values):
    return pd.Series(list(values), dtype="object")


def test_parse_month_valid_and_invalid():
    out = P.parse_month(s("2017-01", "2026-10", "2019-13", "2019-1", "", "Jan-2019"))
    assert out.iloc[0] == pd.Timestamp("2017-01-01")
    assert out.iloc[1] == pd.Timestamp("2026-10-01")
    assert out.iloc[2:].isna().all()


@pytest.mark.parametrize("text,expected", [("93", 93.0), ("366.7", 366.7), ("0", 0.0)])
def test_parse_decimal_valid(text, expected):
    assert P.parse_decimal(s(text)).iloc[0] == expected


@pytest.mark.parametrize("text", ["", "ninety", "1,000", "-5", "1e5", "$500000", "inf", "93 "])
def test_parse_decimal_rejects_non_plain_numbers(text):
    assert pd.isna(P.parse_decimal(s(text)).iloc[0])


def test_parse_decimal_distinguishes_zero_from_missing():
    out = P.parse_decimal(s("0", ""))
    assert out.iloc[0] == 0.0 and pd.isna(out.iloc[1])


def test_parse_year():
    out = P.parse_year(s("1979", "79", "", "19x9"))
    assert out.iloc[0] == 1979
    assert out.iloc[1:].isna().all()


def test_parse_storey_range():
    out = P.parse_storey_range(s("10 TO 12", "01 TO 03", "12 TO 10", "10-12", "00 TO 02"))
    assert (out.loc[0, "storey_lower"], out.loc[0, "storey_upper"], out.loc[0, "storey_mid"]) == (10, 12, 11.0)
    assert out.loc[1, "storey_mid"] == 2.0
    assert out.loc[2:, "storey_lower"].isna().all()  # reversed, wrong separator, zero floor


@pytest.mark.parametrize("text,months", [
    ("61 years 04 months", 61 * 12 + 4),
    ("62 years 01 month", 62 * 12 + 1),
    ("63 years", 63 * 12),
    ("1 year 11 months", 23),
])
def test_parse_remaining_lease_formats(text, months):
    out = P.parse_remaining_lease(s(text))
    assert out.loc[0, "remaining_lease_months"] == months
    assert out.loc[0, "remaining_lease_years"] == pytest.approx(months / 12)


@pytest.mark.parametrize("text", ["", "about seventy", "61", "61 years 12 months", "61 yrs"])
def test_parse_remaining_lease_invalid(text):
    out = P.parse_remaining_lease(s(text))
    assert pd.isna(out.loc[0, "remaining_lease_months"])


def test_normalise_text_trims_and_collapses():
    assert P.normalise_text(s("  SYNTHETIC   ST  1 ")).iloc[0] == "SYNTHETIC ST 1"
