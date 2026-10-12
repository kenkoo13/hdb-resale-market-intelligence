"""Shared test helpers. All data used here is SYNTHETIC (see tests/fixtures/README.md)."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.config import load_config

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_CSV = FIXTURE_DIR / "synthetic_resale_sample.csv"
# Fixture "retrieval" happens in October 2026 so that 2026-10 is the partial month.
FIXTURE_RETRIEVED = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)


def read_fixture() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_CSV, dtype=str, keep_default_na=False)


def make_snapshot(raw_dir: Path, snapshot_id: str, csv_path: Path = FIXTURE_CSV,
                  retrieved: datetime = FIXTURE_RETRIEVED) -> Path:
    """Create a snapshot folder exactly as the ingestion module would."""
    d = raw_dir / snapshot_id
    d.mkdir(parents=True)
    shutil.copy(csv_path, d / "resale_raw.csv")
    data = (d / "resale_raw.csv").read_bytes()
    lines = data.decode("utf-8").splitlines()
    manifest = {
        "snapshot_id": snapshot_id,
        "dataset_id": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        "retrieved_at_utc": retrieved.isoformat(),
        "retrieved_at_local": retrieved.astimezone(ZoneInfo("Asia/Singapore")).isoformat(),
        "timezone": "Asia/Singapore",
        "source_metadata": {"last_updated_at": "synthetic", "declared_types": None},
        "csv_header": lines[0].split(","),
        "row_count": len(lines) - 1,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


@pytest.fixture
def tmp_cfg(tmp_path):
    """Project config whose data/output folders live in a temporary directory."""
    return load_config(root=tmp_path)
