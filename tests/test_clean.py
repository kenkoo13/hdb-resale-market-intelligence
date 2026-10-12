"""Unit tests for cleaning, quarantine and flag rules (src/transformation/clean.py).

Uses the SYNTHETIC fixture; row numbers below refer to tests/fixtures/README.md.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.transformation.clean import clean_snapshot
from tests.conftest import read_fixture

RETRIEVED = datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo("Asia/Singapore"))


@pytest.fixture(scope="module")
def result():
    return clean_snapshot(read_fixture(), RETRIEVED)


def row(df, n):
    return df.loc[df["source_row_number"] == n].iloc[0]


def reasons(result, n):
    q = result.quarantine
    return q.loc[q["source_row_number"] == n, "quarantine_reasons"].iloc[0]


def test_row_accounting(result):
    assert len(result.clean) + len(result.quarantine) == 20
    assert set(result.quarantine["source_row_number"]) == {10, 11, 12, 13, 14}


@pytest.mark.parametrize("n,code", [
    (11, "Q01_missing_resale_price"),
    (12, "Q05_invalid_floor_area"),
    (13, "Q02_invalid_month_format"),
    (14, "Q03_month_outside_coverage"),
    (10, "Q07_suspected_duplicate_artefact"),
])
def test_quarantine_reasons(result, n, code):
    assert code in reasons(result, n)


def test_quarantine_preserves_original_text(result):
    q = result.quarantine
    assert q.loc[q["source_row_number"] == 12, "floor_area_sqm"].iloc[0] == "ninety"


def test_genuine_duplicate_kept_and_annotated(result):
    a, b = row(result.clean, 7), row(result.clean, 8)
    assert a["duplicate_group_size"] == 2 and b["duplicate_group_size"] == 2


def test_2017_artefact_keeps_first_copy(result):
    first = row(result.clean, 9)
    assert first["resale_price_sgd"] == 470000 and first["duplicate_group_size"] == 1


def test_unparseable_remaining_lease_kept_and_flagged(result):
    r = row(result.clean, 15)
    assert r["flag_invalid_remaining_lease"] and pd.isna(r["remaining_lease_months"])


def test_whitespace_and_case_normalised(result):
    r = row(result.clean, 16)
    assert r["town"] == "BEDOK" and r["street_name"] == "SYNTHETIC ST 14"


def test_implausible_floor_area_kept_and_flagged(result):
    r = row(result.clean, 17)
    assert r["flag_implausible_floor_area"] and r["floor_area_sqm_num"] == 15.0


def test_lease_inconsistency_flagged(result):
    assert row(result.clean, 18)["flag_lease_inconsistent"]
    assert not row(result.clean, 1)["flag_lease_inconsistent"]


def test_partial_month_flag(result):
    assert row(result.clean, 19)["is_partial_month"]
    assert result.clean["is_partial_month"].sum() == 1


def test_flat_model_case_unified(result):
    assert row(result.clean, 20)["flat_model"] == "Model A"


def test_derived_fields(result):
    r = row(result.clean, 1)  # 2019-03, 67 sqm, 300,000, lease 1980, "60 years 05 months"
    assert r["price_per_sqm_sgd"] == pytest.approx(300000 / 67)
    assert r["remaining_lease_months"] == 725
    # derived = 99 - ((2019 - 1980) + (3 - 1)/12)
    assert r["derived_remaining_lease_years"] == pytest.approx(99 - (39 + 2 / 12))
    assert r["storey_mid"] == 5.0


def test_lease_commence_after_transaction_is_nulled_and_flagged():
    raw = read_fixture().iloc[[0]].copy()
    raw["lease_commence_date"] = "2030"
    out = clean_snapshot(raw, RETRIEVED).clean.iloc[0]
    assert out["flag_invalid_lease_commence"] and pd.isna(out["lease_commence_year"])


def test_rule_counts_match_outputs(result):
    rc = result.rule_counts
    assert rc["Q07_suspected_duplicate_artefact"] == 1
    assert rc["F_is_partial_month"] == int(result.clean["is_partial_month"].sum())


def test_idempotent(result):
    again = clean_snapshot(read_fixture(), RETRIEVED)
    pd.testing.assert_frame_equal(result.clean, again.clean)
    pd.testing.assert_frame_equal(result.quarantine, again.quarantine)
