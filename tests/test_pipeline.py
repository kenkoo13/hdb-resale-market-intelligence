"""Pipeline-level tests: output schema, refresh failure safety, idempotency (SYNTHETIC data)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.pipeline import CLEAN_FILE, QUARANTINE_FILE, RUN_INFO_FILE, process_snapshot
from src.validation.schema import EXPECTED_COLUMNS, SchemaValidationError
from tests.conftest import make_snapshot, read_fixture

REQUIRED_CLEAN_COLUMNS = {
    "source_row_number", *EXPECTED_COLUMNS, "month_date", "year", "floor_area_sqm_num",
    "resale_price_sgd", "storey_lower", "storey_upper", "storey_mid", "lease_commence_year",
    "remaining_lease_months", "remaining_lease_years", "price_per_sqm_sgd",
    "is_partial_month", "duplicate_group_size", "flag_lease_inconsistent",
}


def test_outputs_written_with_expected_schema(tmp_cfg):
    snap = make_snapshot(tmp_cfg.raw_dir, "20261012T010000Z")
    info = process_snapshot(snap, tmp_cfg)
    clean = pd.read_parquet(tmp_cfg.processed_dir / CLEAN_FILE)
    assert REQUIRED_CLEAN_COLUMNS <= set(clean.columns)
    assert pd.api.types.is_float_dtype(clean["resale_price_sgd"])
    assert pd.api.types.is_datetime64_any_dtype(clean["month_date"])
    q = pd.read_csv(tmp_cfg.processed_dir / QUARANTINE_FILE, dtype=str)
    assert set(EXPECTED_COLUMNS) | {"quarantine_reasons"} <= set(q.columns)
    assert info["clean_rows"] + info["quarantined_rows"] == info["raw_rows"] == 20
    assert (tmp_cfg.outputs_dir / "data_quality" / "dq_report.md").exists()
    rep = json.loads((tmp_cfg.outputs_dir / "data_quality" / "dq_report.json").read_text())
    assert rep["counts"]["quarantined_rows"] == 5


def test_schema_change_blocks_and_preserves_previous_outputs(tmp_cfg, tmp_path):
    good = make_snapshot(tmp_cfg.raw_dir, "20261011T010000Z")
    process_snapshot(good, tmp_cfg)
    before = (tmp_cfg.processed_dir / CLEAN_FILE).read_bytes()
    before_info = (tmp_cfg.processed_dir / RUN_INFO_FILE).read_text()

    broken_csv = tmp_path / "broken.csv"
    read_fixture().drop(columns=["remaining_lease"]).to_csv(broken_csv, index=False)
    bad = make_snapshot(tmp_cfg.raw_dir, "20261012T010000Z", csv_path=broken_csv)
    with pytest.raises(SchemaValidationError, match="remaining_lease"):
        process_snapshot(bad, tmp_cfg)

    assert (tmp_cfg.processed_dir / CLEAN_FILE).read_bytes() == before
    assert (tmp_cfg.processed_dir / RUN_INFO_FILE).read_text() == before_info
    assert not list(tmp_cfg.processed_dir.glob(".*.tmp"))


def test_row_count_collapse_blocks(tmp_cfg, tmp_path):
    process_snapshot(make_snapshot(tmp_cfg.raw_dir, "20261011T010000Z"), tmp_cfg)
    small = tmp_path / "small.csv"
    read_fixture().head(5).to_csv(small, index=False)
    with pytest.raises(SchemaValidationError, match="Row count fell"):
        process_snapshot(make_snapshot(tmp_cfg.raw_dir, "20261012T010000Z", csv_path=small), tmp_cfg)


def test_reprocessing_same_snapshot_is_idempotent(tmp_cfg):
    snap = make_snapshot(tmp_cfg.raw_dir, "20261012T010000Z")
    process_snapshot(snap, tmp_cfg)
    first = pd.read_parquet(tmp_cfg.processed_dir / CLEAN_FILE)
    process_snapshot(snap, tmp_cfg)
    second = pd.read_parquet(tmp_cfg.processed_dir / CLEAN_FILE)
    pd.testing.assert_frame_equal(first, second)
    assert len(second) == 15  # no accumulation across runs
