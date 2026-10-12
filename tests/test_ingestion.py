"""Unit tests for the data.gov.sg client using a fake HTTP session (no network)."""
from __future__ import annotations

import json

import pytest
import requests

from src.ingestion.datagov_client import (
    IngestionError, create_snapshot, list_snapshots, read_manifest)
from tests.conftest import FIXTURE_CSV, FIXTURE_RETRIEVED

DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
CSV_BYTES = FIXTURE_CSV.read_bytes()


class FakeResponse:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code = status
        self._body = body
        self._content = content
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def metadata_body(dataset_id=DATASET_ID):
    return {"code": 0, "errorMsg": "", "data": {
        "datasetId": dataset_id, "name": "synthetic", "managedBy": "HDB",
        "lastUpdatedAt": "2026-10-12T02:10:19+08:00",
        "columnMetadata": {"order": ["c1"], "map": {"c1": "month"},
                           "metaMapping": {"c1": {"name": "month", "dataType": "Month (YYYY-MM)"}}}}}


class FakeSession:
    """Routes URLs to queued responses; records calls."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def get(self, url, timeout=None, stream=False):
        self.calls.append(url)
        for key, queue in self.routes.items():
            if key in url:
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"unexpected URL {url}")


def happy_routes(**overrides):
    routes = {
        "metadata": [FakeResponse(body=metadata_body())],
        "initiate-download": [FakeResponse(201, {"code": 0, "data": {"message": "ok"}})],
        "poll-download": [FakeResponse(body={"code": 0, "data": {"status": "DOWNLOAD_SUCCESS",
                                                                "url": "https://s3.example/file.csv"}})],
        "s3.example": [FakeResponse(content=CSV_BYTES)],
    }
    routes.update(overrides)
    return routes


def no_sleep(_):
    pass


def test_successful_snapshot_writes_csv_and_manifest(tmp_cfg):
    snap = create_snapshot(tmp_cfg, FakeSession(happy_routes()), FIXTURE_RETRIEVED, no_sleep)
    assert (snap / "resale_raw.csv").read_bytes() == CSV_BYTES
    m = read_manifest(snap)
    assert m["dataset_id"] == DATASET_ID
    assert m["row_count"] == 20
    assert m["csv_header"][0] == "month"
    assert m["retrieved_at_local"].endswith("+08:00")
    assert len(m["sha256"]) == 64
    assert list_snapshots(tmp_cfg.raw_dir) == [snap]


def test_retryable_error_then_success(tmp_cfg):
    routes = happy_routes(metadata=[FakeResponse(503), requests.ConnectionError("boom"),
                                    FakeResponse(body=metadata_body())])
    session = FakeSession(routes)
    create_snapshot(tmp_cfg, session, FIXTURE_RETRIEVED, no_sleep)
    assert sum("metadata" in c for c in session.calls) == 3


def test_retries_exhausted_raises_and_leaves_no_snapshot(tmp_cfg):
    routes = happy_routes(metadata=[FakeResponse(503)])
    with pytest.raises(IngestionError, match="Failed after 3 attempts"):
        create_snapshot(tmp_cfg, FakeSession(routes), FIXTURE_RETRIEVED, no_sleep)
    assert list(tmp_cfg.raw_dir.iterdir()) == []  # partial dir cleaned up


def test_client_error_not_retried(tmp_cfg):
    session = FakeSession(happy_routes(metadata=[FakeResponse(404, {"code": 1})]))
    with pytest.raises(IngestionError, match="HTTP 404"):
        create_snapshot(tmp_cfg, session, FIXTURE_RETRIEVED, no_sleep)
    assert len(session.calls) == 1


def test_api_error_code_raises(tmp_cfg):
    routes = happy_routes(metadata=[FakeResponse(body={"code": 17, "errorMsg": "nope"})])
    with pytest.raises(IngestionError, match="Unexpected API response"):
        create_snapshot(tmp_cfg, FakeSession(routes), FIXTURE_RETRIEVED, no_sleep)


def test_wrong_dataset_id_rejected(tmp_cfg):
    routes = happy_routes(metadata=[FakeResponse(body=metadata_body("d_other"))])
    with pytest.raises(IngestionError, match="dataset ID"):
        create_snapshot(tmp_cfg, FakeSession(routes), FIXTURE_RETRIEVED, no_sleep)


def test_poll_never_ready_raises(tmp_cfg):
    routes = happy_routes(**{"poll-download": [FakeResponse(body={"code": 0, "data": {"status": "PENDING"}})]})
    with pytest.raises(IngestionError, match="not ready"):
        create_snapshot(tmp_cfg, FakeSession(routes), FIXTURE_RETRIEVED, no_sleep)
    assert list(tmp_cfg.raw_dir.iterdir()) == []


def test_download_http_error_leaves_no_snapshot(tmp_cfg):
    routes = happy_routes(**{"s3.example": [FakeResponse(403)]})
    with pytest.raises(IngestionError):
        create_snapshot(tmp_cfg, FakeSession(routes), FIXTURE_RETRIEVED, no_sleep)
    assert list_snapshots(tmp_cfg.raw_dir) == []
