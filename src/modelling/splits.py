"""Chronological train / validation / test split (docs/MODEL_CARD.md §3).

Boundaries are derived from the snapshot's last full month L so a refresh moves
the windows forward automatically:
    train      : first month .. L-24
    validation : L-23 .. L-12   (12 months)
    test       : L-11 .. L      (12 months)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BLOCK_MONTHS = 12


@dataclass(frozen=True)
class ChronoSplit:
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def describe(self, df: pd.DataFrame) -> dict:
        parts = self.assign(df)
        return {name: {"start": f"{g['month_date'].min():%Y-%m}", "end": f"{g['month_date'].max():%Y-%m}",
                       "rows": int(len(g)), "months": int(g["month_date"].nunique())}
                for name, g in parts.items()}

    def assign(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        md = df["month_date"]
        return {
            "train": df.loc[md <= self.train_end],
            "validation": df.loc[(md >= self.val_start) & (md <= self.val_end)],
            "test": df.loc[(md >= self.test_start) & (md <= self.test_end)],
        }


def make_split(df: pd.DataFrame) -> ChronoSplit:
    """Build the split from the last full month present in ``df`` (partial month must be excluded)."""
    if df["is_partial_month"].any():
        raise ValueError("Partial-month rows must be removed before splitting (DEC-008)")
    last = df["month_date"].max()
    test_start = last - pd.DateOffset(months=BLOCK_MONTHS - 1)
    val_end = test_start - pd.DateOffset(months=1)
    val_start = val_end - pd.DateOffset(months=BLOCK_MONTHS - 1)
    return ChronoSplit(train_end=val_start - pd.DateOffset(months=1), val_start=val_start,
                       val_end=val_end, test_start=test_start, test_end=last)
