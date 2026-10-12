"""Pipeline entry point: ingest -> validate -> clean -> publish processed outputs.

Usage
    python -m src.pipeline                    # download a new snapshot, then process it
    python -m src.pipeline --skip-download    # reprocess the latest existing snapshot
    python -m src.pipeline --snapshot 20261012T004500Z

Stages and gates (DEC-003, DEC-006)
    1. Ingest a full snapshot into ``data/raw/<snapshot_id>/`` (immutable).
    2. Blocking gates: header contract, zero rows, row-count drop vs the previous
       snapshot, CSV row count vs manifest. Any failure -> exit code 2, processed
       outputs untouched.
    3. Clean and flag (``src/transformation/clean.py``).
    4. Publish: every output is written to a temporary file first and moved into
       place with ``os.replace`` only after all files were written successfully.

Outputs
    data/processed/transactions_clean.parquet   (git-ignored, ~240k rows)
    data/processed/quarantine.csv               (original text + reason codes)
    data/processed/run_info.json                (snapshot id, counts, timestamps)
    outputs/data_quality/dq_report.json|.md     (committed; small)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import ProjectConfig, load_config
from src.ingestion.datagov_client import (
    RAW_FILENAME, IngestionError, create_snapshot, list_snapshots, read_manifest)
from src.transformation.clean import clean_snapshot
from src.validation.quality_report import build_report, render_markdown
from src.validation.schema import (
    EXPECTED_COLUMNS, GateResult, SchemaValidationError, check_declared_types,
    check_header, check_row_count)

log = logging.getLogger("pipeline")

CLEAN_FILE = "transactions_clean.parquet"
QUARANTINE_FILE = "quarantine.csv"
RUN_INFO_FILE = "run_info.json"


def read_raw(snapshot_dir: Path) -> pd.DataFrame:
    """Read the raw CSV with every field as text; no NA inference (DEC-010)."""
    return pd.read_csv(snapshot_dir / RAW_FILENAME, dtype=str, keep_default_na=False,
                       encoding="utf-8")


def run_gates(raw: pd.DataFrame, manifest: dict[str, Any], previous: dict[str, Any] | None,
              cfg: ProjectConfig) -> GateResult:
    gates = check_header(list(raw.columns))
    gates.extend(check_declared_types(manifest["source_metadata"].get("declared_types")))
    gates.extend(check_row_count(len(raw), previous["row_count"] if previous else None,
                                 cfg.min_row_ratio_vs_previous))
    if len(raw) != manifest["row_count"]:
        gates.blocking.append(f"pandas read {len(raw):,} rows but manifest recorded {manifest['row_count']:,}")
    return gates


def _publish(files: dict[Path, Any]) -> None:
    """Write all outputs to temp paths, then atomically move each into place."""
    temps: list[tuple[Path, Path]] = []
    try:
        for target, payload in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.tmp")
            if isinstance(payload, pd.DataFrame):
                if target.suffix == ".parquet":
                    payload.to_parquet(tmp, index=False)
                else:
                    payload.to_csv(tmp, index=False, encoding="utf-8")
            else:
                tmp.write_text(payload, encoding="utf-8")
            temps.append((tmp, target))
    except Exception:
        for tmp, _ in temps:
            tmp.unlink(missing_ok=True)
        raise
    for tmp, target in temps:
        os.replace(tmp, target)


def process_snapshot(snapshot_dir: Path, cfg: ProjectConfig) -> dict[str, Any]:
    manifest = read_manifest(snapshot_dir)
    snapshots = list_snapshots(cfg.raw_dir)
    earlier = [p for p in snapshots if p.name < snapshot_dir.name]
    previous = read_manifest(earlier[-1]) if earlier else None

    raw = read_raw(snapshot_dir)
    gates = run_gates(raw, manifest, previous, cfg)
    for w in gates.warnings:
        log.warning("Gate warning: %s", w)
    if not gates.passed:
        raise SchemaValidationError("; ".join(gates.blocking))

    retrieved_local = datetime.fromisoformat(manifest["retrieved_at_local"])
    result = clean_snapshot(raw[EXPECTED_COLUMNS], retrieved_local)
    report = build_report(raw, result, manifest, gates, previous)

    run_info = {
        "snapshot_id": manifest["snapshot_id"],
        "dataset_id": manifest["dataset_id"],
        "retrieved_at_local": manifest["retrieved_at_local"],
        "source_last_updated_at": manifest["source_metadata"].get("last_updated_at"),
        "sha256": manifest["sha256"],
        "processed_at_local": datetime.now(retrieved_local.tzinfo).isoformat(),
        **report["counts"],
        "first_month": report["coverage"]["first_month"],
        "last_month": report["coverage"]["last_month"],
        "partial_months": report["coverage"]["partial_months"],
    }
    dq_dir = cfg.outputs_dir / "data_quality"
    _publish({
        cfg.processed_dir / CLEAN_FILE: result.clean,
        cfg.processed_dir / QUARANTINE_FILE: result.quarantine,
        cfg.processed_dir / RUN_INFO_FILE: json.dumps(run_info, indent=2, default=str),
        dq_dir / "dq_report.json": json.dumps(report, indent=2, default=str),
        dq_dir / "dq_report.md": render_markdown(report),
    })
    log.info("Processed %s: %d clean, %d quarantined", manifest["snapshot_id"],
             len(result.clean), len(result.quarantine))
    return run_info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--skip-download", action="store_true", help="reprocess the latest snapshot")
    group.add_argument("--snapshot", help="reprocess a specific snapshot id")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()

    try:
        if args.snapshot:
            snapshot_dir = cfg.raw_dir / args.snapshot
            if not snapshot_dir.exists():
                log.error("Snapshot %s not found", args.snapshot)
                return 1
        elif args.skip_download:
            snaps = list_snapshots(cfg.raw_dir)
            if not snaps:
                log.error("No snapshots in %s; run without --skip-download", cfg.raw_dir)
                return 1
            snapshot_dir = snaps[-1]
        else:
            snapshot_dir = create_snapshot(cfg)
        info = process_snapshot(snapshot_dir, cfg)
    except IngestionError as exc:
        log.error("Ingestion failed; previous outputs left unchanged: %s", exc)
        return 2
    except SchemaValidationError as exc:
        log.error("Validation gate failed; previous outputs left unchanged: %s", exc)
        return 2
    print(json.dumps(info, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
