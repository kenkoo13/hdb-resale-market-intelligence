"""Download a full, immutable snapshot of the HDB resale dataset from data.gov.sg.

Purpose
    Implements DEC-002 (bulk CSV via initiate/poll download API) and DEC-003
    (full replacement snapshots). Each run creates ``data/raw/<snapshot_id>/`` with:

    * ``resale_raw.csv`` - the source file byte-for-byte as served.
    * ``manifest.json``  - retrieval timestamps, dataset ID, publisher metadata
      (last updated, declared coverage, declared columns), CSV header, data row
      count, byte size and SHA-256.

Inputs
    :class:`src.config.ProjectConfig` (dataset ID, endpoint templates, timeouts,
    retry policy). A ``requests.Session`` and ``sleep`` function can be injected
    so tests can mock the network without real HTTP calls.

Error handling
    * Network errors, timeouts, HTTP 429 and 5xx are retried ``max_retries`` times
      with linear back-off; other 4xx fail immediately.
    * An API body whose ``code`` is not 0, or that lacks the expected keys, raises
      :class:`IngestionError` (we do not guess at a changed API contract).
    * The download is written to a ``.partial`` directory and renamed only when
      complete, so an interrupted run never leaves a half-written snapshot that a
      later stage could mistake for valid input.

Dependencies
    ``requests``. No API key is required for this public dataset.

Limitations
    The signed download URL expires after ~1 hour; it is used immediately.
    Schema *validation* is deliberately not done here (see ``src/validation``),
    so ingestion stays a faithful copy of the source.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests

from src.config import ProjectConfig

log = logging.getLogger(__name__)

RAW_FILENAME = "resale_raw.csv"
MANIFEST_FILENAME = "manifest.json"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class IngestionError(RuntimeError):
    """Raised when the source cannot be retrieved or its API contract changed."""


def _get_json(
    session: requests.Session,
    url: str,
    cfg: ProjectConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """GET a data.gov.sg JSON endpoint with retries; return the ``data`` object."""
    last_error: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            resp = session.get(url, timeout=cfg.timeout_seconds)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        else:
            if resp.status_code in RETRYABLE_STATUS:
                last_error = IngestionError(f"HTTP {resp.status_code} from {url}")
            elif not 200 <= resp.status_code < 300:  # initiate-download answers 201
                raise IngestionError(f"HTTP {resp.status_code} from {url}: {resp.text[:200]}")
            else:
                try:
                    body = resp.json()
                except ValueError as exc:
                    raise IngestionError(f"Non-JSON response from {url}") from exc
                if body.get("code") != 0 or "data" not in body:
                    raise IngestionError(
                        f"Unexpected API response from {url}: code={body.get('code')!r} "
                        f"errorMsg={body.get('errorMsg')!r}"
                    )
                return body["data"]
        if attempt < cfg.max_retries:
            wait = cfg.backoff_seconds * attempt
            log.warning("Attempt %d/%d failed for %s (%s); retrying in %.0fs",
                        attempt, cfg.max_retries, url, last_error, wait)
            sleep(wait)
    raise IngestionError(f"Failed after {cfg.max_retries} attempts: {url}") from last_error


def fetch_metadata(session: requests.Session, cfg: ProjectConfig,
                   sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Return a compact summary of the publisher's dataset metadata."""
    data = _get_json(session, cfg.metadata_url, cfg, sleep)
    try:
        cols = data["columnMetadata"]
        ordered = [cols["map"][cid] for cid in cols["order"]]
        declared_types = {cols["metaMapping"][cid]["name"]: cols["metaMapping"][cid]["dataType"]
                          for cid in cols["order"]}
    except (KeyError, TypeError) as exc:
        raise IngestionError("Metadata response missing columnMetadata") from exc
    return {
        "dataset_id": data.get("datasetId"),
        "name": data.get("name"),
        "managed_by": data.get("managedBy"),
        "last_updated_at": data.get("lastUpdatedAt"),
        "coverage_start": data.get("coverageStart"),
        "coverage_end": data.get("coverageEnd"),
        "declared_columns": ordered,
        "declared_types": declared_types,
    }


def get_download_url(session: requests.Session, cfg: ProjectConfig,
                     sleep: Callable[[float], None] = time.sleep) -> str:
    """Initiate the bulk download and poll until a signed URL is ready."""
    _get_json(session, cfg.initiate_url, cfg, sleep)
    for _ in range(cfg.poll_attempts):
        data = _get_json(session, cfg.poll_url, cfg, sleep)
        if data.get("status") == "DOWNLOAD_SUCCESS" and data.get("url"):
            return data["url"]
        sleep(cfg.poll_interval_seconds)
    raise IngestionError(f"Download not ready after {cfg.poll_attempts} polls")


def _stream_to_file(session: requests.Session, url: str, dest: Path, cfg: ProjectConfig) -> str:
    """Stream ``url`` to ``dest``; return the SHA-256 hex digest."""
    sha = hashlib.sha256()
    try:
        with session.get(url, stream=True, timeout=cfg.timeout_seconds) as resp:
            if resp.status_code != 200:
                raise IngestionError(f"HTTP {resp.status_code} downloading CSV")
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
                    sha.update(chunk)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise IngestionError(f"Network error downloading CSV: {exc}") from exc
    return sha.hexdigest()


def _count_csv(path: Path) -> tuple[list[str], int]:
    """Return (header, number of data rows) using the csv module (handles quoted commas)."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        n = sum(1 for _ in reader)
    return header, n


def create_snapshot(
    cfg: ProjectConfig,
    session: requests.Session | None = None,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Download the dataset into a new snapshot directory and return its path."""
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    snapshot_id = now.strftime("%Y%m%dT%H%M%SZ")
    final_dir = cfg.raw_dir / snapshot_id
    if final_dir.exists():
        raise IngestionError(f"Snapshot {snapshot_id} already exists")
    partial_dir = cfg.raw_dir / f".{snapshot_id}.partial"
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    partial_dir.mkdir(parents=True)

    try:
        metadata = fetch_metadata(session, cfg, sleep)
        if metadata["dataset_id"] != cfg.dataset_id:
            raise IngestionError(
                f"Metadata dataset ID {metadata['dataset_id']!r} != configured {cfg.dataset_id!r}")
        url = get_download_url(session, cfg, sleep)
        raw_path = partial_dir / RAW_FILENAME
        sha256 = _stream_to_file(session, url, raw_path, cfg)
        header, row_count = _count_csv(raw_path)
        manifest = {
            "snapshot_id": snapshot_id,
            "dataset_id": cfg.dataset_id,
            "retrieved_at_utc": now.isoformat(),
            "retrieved_at_local": now.astimezone(ZoneInfo(cfg.timezone)).isoformat(),
            "timezone": cfg.timezone,
            "source_metadata": metadata,
            "csv_header": header,
            "row_count": row_count,
            "bytes": raw_path.stat().st_size,
            "sha256": sha256,
        }
        (partial_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        partial_dir.rename(final_dir)
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    log.info("Snapshot %s: %d rows, sha256=%s", snapshot_id, row_count, sha256[:12])
    return final_dir


def list_snapshots(raw_dir: Path) -> list[Path]:
    """Completed snapshot directories (those with a manifest), oldest first."""
    if not raw_dir.exists():
        return []
    return sorted(p for p in raw_dir.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and (p / MANIFEST_FILENAME).exists())


def read_manifest(snapshot_dir: Path) -> dict[str, Any]:
    return json.loads((snapshot_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
