"""Project configuration.

Purpose
    Central place for the source identifier, endpoints, HTTP behaviour, validation
    thresholds and paths, so no module hard-codes them (brief §6.1).

Inputs
    Built-in defaults below, optionally overridden by ``config/project_config.yaml``
    (git-ignored; see ``config/project_config.example.yaml``). Overrides are merged
    one level deep per section.

Outputs
    A :class:`ProjectConfig` with absolute paths resolved against the repository root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS: dict[str, dict[str, Any]] = {
    "source": {
        "dataset_id": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        "metadata_url": "https://api-production.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata",
        "initiate_url": "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/initiate-download",
        "poll_url": "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download",
    },
    "http": {
        "timeout_seconds": 60,
        "max_retries": 3,
        "backoff_seconds": 2,
        "poll_attempts": 10,
        "poll_interval_seconds": 3,
    },
    "validation": {"min_row_ratio_vs_previous": 0.98},
    "paths": {
        "raw_dir": "data/raw",
        "processed_dir": "data/processed",
        "curated_dir": "data/curated",
        "outputs_dir": "outputs",
    },
    "timezone": {"name": "Asia/Singapore"},
    "random_seed": {"value": 42},
}


@dataclass(frozen=True)
class ProjectConfig:
    dataset_id: str
    metadata_url: str
    initiate_url: str
    poll_url: str
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float
    poll_attempts: int
    poll_interval_seconds: float
    min_row_ratio_vs_previous: float
    raw_dir: Path
    processed_dir: Path
    curated_dir: Path
    outputs_dir: Path
    timezone: str = "Asia/Singapore"
    random_seed: int = 42
    extra: dict[str, Any] = field(default_factory=dict)


def load_config(path: Path | None = None, root: Path = REPO_ROOT) -> ProjectConfig:
    """Load defaults, apply an optional YAML override, and resolve paths."""
    merged = {k: dict(v) for k, v in DEFAULTS.items()}
    path = path or root / "config" / "project_config.yaml"
    if path.exists():
        override = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for section, values in override.items():
            if isinstance(values, dict):
                merged.setdefault(section, {}).update(values)
            else:  # scalar top-level keys (timezone, random_seed) in the example file
                key = "name" if section == "timezone" else "value"
                merged.setdefault(section, {})[key] = values

    src, http, paths = merged["source"], merged["http"], merged["paths"]
    fmt = {"dataset_id": src["dataset_id"]}
    return ProjectConfig(
        dataset_id=src["dataset_id"],
        metadata_url=src["metadata_url"].format(**fmt),
        initiate_url=src["initiate_url"].format(**fmt),
        poll_url=src["poll_url"].format(**fmt),
        timeout_seconds=float(http["timeout_seconds"]),
        max_retries=int(http["max_retries"]),
        backoff_seconds=float(http["backoff_seconds"]),
        poll_attempts=int(http["poll_attempts"]),
        poll_interval_seconds=float(http["poll_interval_seconds"]),
        min_row_ratio_vs_previous=float(merged["validation"]["min_row_ratio_vs_previous"]),
        raw_dir=root / paths["raw_dir"],
        processed_dir=root / paths["processed_dir"],
        curated_dir=root / paths["curated_dir"],
        outputs_dir=root / paths["outputs_dir"],
        timezone=merged["timezone"]["name"],
        random_seed=int(merged["random_seed"]["value"]),
    )
