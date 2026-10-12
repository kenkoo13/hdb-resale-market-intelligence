"""Unit tests for source schema contract and snapshot gates (src/validation/schema.py)."""
from src.validation.schema import (
    EXPECTED_COLUMNS, EXPECTED_DECLARED_TYPES, check_declared_types, check_header, check_row_count)


def test_expected_header_passes_cleanly():
    res = check_header(list(EXPECTED_COLUMNS))
    assert res.passed and not res.warnings


def test_missing_column_blocks():
    res = check_header([c for c in EXPECTED_COLUMNS if c != "remaining_lease"])
    assert not res.passed
    assert "remaining_lease" in res.blocking[0]


def test_renamed_column_blocks():
    header = ["resale_price_sgd" if c == "resale_price" else c for c in EXPECTED_COLUMNS]
    assert not check_header(header).passed


def test_extra_column_warns_only():
    res = check_header(EXPECTED_COLUMNS + ["latitude"])
    assert res.passed and any("latitude" in w for w in res.warnings)


def test_reordered_columns_warn_only():
    res = check_header(list(reversed(EXPECTED_COLUMNS)))
    assert res.passed and any("order" in w for w in res.warnings)


def test_duplicate_column_names_block():
    assert not check_header(EXPECTED_COLUMNS + ["town"]).passed


def test_declared_type_change_warns():
    declared = dict(EXPECTED_DECLARED_TYPES, floor_area_sqm="Numeric")
    res = check_declared_types(declared)
    assert res.passed and any("floor_area_sqm" in w for w in res.warnings)


def test_row_count_gates():
    assert not check_row_count(0, None, 0.98).passed
    assert check_row_count(100, None, 0.98).passed            # first snapshot
    assert check_row_count(1010, 1000, 0.98).passed           # growth
    small_drop = check_row_count(990, 1000, 0.98)
    assert small_drop.passed and small_drop.warnings          # within tolerance, warned
    assert not check_row_count(900, 1000, 0.98).passed        # large drop blocks
