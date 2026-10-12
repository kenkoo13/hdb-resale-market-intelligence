"""Shared loading and windowing helpers for the analysis layer.

Purpose
    One definition of the "analysis-ready" population and the analysis windows, so
    descriptive statistics, hypothesis tests and models all use identical filters
    (docs/HYPOTHESIS_REGISTER.md §1).

Definitions
    * Analysis-ready: clean rows (Q01-Q07 already removed) with ``is_partial_month == False``.
    * Recent window: the ``RECENT_WINDOW_MONTHS`` full months ending at the last full month.
    * Latest 12 months: the 12 full months ending at the last full month.
    * Building: ``block + " " + street_name`` - the clustering unit for standard errors.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ProjectConfig

RECENT_WINDOW_MONTHS = 24
MIN_SEGMENT_N = 30  # segments with fewer transactions are labelled low-sample

STOREY_BAND_ORDER_KEY = "storey_lower"


@dataclass(frozen=True)
class Windows:
    first_full_month: pd.Timestamp
    last_full_month: pd.Timestamp
    recent_start: pd.Timestamp
    latest12_start: pd.Timestamp

    def label(self, start: pd.Timestamp) -> str:
        return f"{start:%Y-%m} to {self.last_full_month:%Y-%m}"


def load_clean(cfg: ProjectConfig) -> pd.DataFrame:
    path = cfg.processed_dir / "transactions_clean.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `python -m src.pipeline` first")
    return pd.read_parquet(path)


def analysis_ready(clean: pd.DataFrame) -> pd.DataFrame:
    df = clean.loc[~clean["is_partial_month"]].copy()
    df["building"] = df["block"].fillna("?") + " " + df["street_name"].fillna("?")
    df["log_price"] = np.log(df["resale_price_sgd"])
    return df


def get_windows(df: pd.DataFrame) -> Windows:
    last = df["month_date"].max()
    return Windows(
        first_full_month=df["month_date"].min(),
        last_full_month=last,
        recent_start=last - pd.DateOffset(months=RECENT_WINDOW_MONTHS - 1),
        latest12_start=last - pd.DateOffset(months=11),
    )


def in_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return df.loc[df["month_date"].between(start, end)]


def run_snapshot_id(cfg: ProjectConfig) -> str:
    import json
    info = json.loads(Path(cfg.processed_dir / "run_info.json").read_text(encoding="utf-8"))
    return info["snapshot_id"]
