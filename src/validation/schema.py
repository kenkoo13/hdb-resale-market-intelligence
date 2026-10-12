"""Source schema contract and snapshot-level gates.

Purpose
    Detects source changes *before* any transformation runs, so a changed schema or
    a truncated download stops the pipeline instead of silently producing wrong
    BI inputs (DEC-006).

Contract (verified against the live source 2026-10-12)
    * The CSV header must contain every column in ``EXPECTED_COLUMNS``.
      Missing column -> BLOCKING.
    * Extra columns -> WARNING (recorded and ignored; downstream code selects
      only expected columns).
    * Column order differing from the expected order -> WARNING.
    * Publisher-declared data types differing from ``EXPECTED_DECLARED_TYPES``
      -> WARNING (the CSV is parsed as text regardless, so a type label change is
      informative, not breaking).
    * Zero data rows -> BLOCKING.
    * Row count below ``min_ratio`` x the previous snapshot -> BLOCKING
      (the dataset is cumulative, so a large drop suggests a truncated or
      broken publication rather than genuine removals).
"""
from __future__ import annotations

from dataclasses import dataclass, field

EXPECTED_COLUMNS: list[str] = [
    "month", "town", "flat_type", "block", "street_name", "storey_range",
    "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease", "resale_price",
]

EXPECTED_DECLARED_TYPES: dict[str, str] = {
    "month": "Month (YYYY-MM)", "town": "Text", "flat_type": "Text", "block": "Text",
    "street_name": "Text", "storey_range": "Text", "floor_area_sqm": "Text",
    "flat_model": "Text", "lease_commence_date": "Text", "remaining_lease": "Text",
    "resale_price": "Numeric",
}


@dataclass
class GateResult:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.blocking

    def extend(self, other: "GateResult") -> "GateResult":
        self.blocking += other.blocking
        self.warnings += other.warnings
        return self


class SchemaValidationError(RuntimeError):
    """Raised by the pipeline when a blocking gate fails."""


def check_header(header: list[str]) -> GateResult:
    res = GateResult()
    cleaned = [h.strip() for h in header]
    missing = [c for c in EXPECTED_COLUMNS if c not in cleaned]
    extra = [c for c in cleaned if c not in EXPECTED_COLUMNS]
    if missing:
        res.blocking.append(f"Missing expected columns: {missing}")
    if extra:
        res.warnings.append(f"Unexpected extra columns ignored: {extra}")
    if not missing and [c for c in cleaned if c in EXPECTED_COLUMNS] != EXPECTED_COLUMNS:
        res.warnings.append("Column order differs from the expected order")
    if len(set(cleaned)) != len(cleaned):
        res.blocking.append("Duplicate column names in header")
    return res


def check_declared_types(declared: dict[str, str] | None) -> GateResult:
    res = GateResult()
    if not declared:
        res.warnings.append("Publisher metadata did not include declared column types")
        return res
    for col, expected in EXPECTED_DECLARED_TYPES.items():
        actual = declared.get(col)
        if actual is not None and actual != expected:
            res.warnings.append(f"Declared type for {col!r} changed: {expected!r} -> {actual!r}")
    return res


def check_row_count(row_count: int, previous_row_count: int | None, min_ratio: float) -> GateResult:
    res = GateResult()
    if row_count <= 0:
        res.blocking.append("Snapshot contains zero data rows")
    elif previous_row_count:
        ratio = row_count / previous_row_count
        if ratio < min_ratio:
            res.blocking.append(
                f"Row count fell to {row_count:,} from {previous_row_count:,} "
                f"(ratio {ratio:.4f} < threshold {min_ratio})")
        elif row_count < previous_row_count:
            res.warnings.append(
                f"Row count fell slightly: {previous_row_count:,} -> {row_count:,}")
    return res
