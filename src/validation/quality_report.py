"""Compute the data-quality report for one snapshot.

Purpose
    Produces the *measured* figures quoted in docs/DATA_QUALITY.md: record counts,
    blank rates, parse failures, category inventories, month coverage and gaps,
    duplicate structure, quarantine counts, warning flags and the remaining-lease
    consistency check. Nothing in the report is estimated or hand-entered.

Outputs
    A JSON-serialisable dict (``build_report``) and a Markdown rendering
    (``render_markdown``), written by the pipeline to ``outputs/data_quality/``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.transformation import parsers as P
from src.transformation.clean import CleanResult
from src.validation.schema import EXPECTED_COLUMNS, GateResult


def _field_profile(raw: pd.DataFrame) -> list[dict[str, Any]]:
    parse_fail = {
        "month": P.parse_month(raw["month"].str.strip()).isna(),
        "floor_area_sqm": P.parse_decimal(raw["floor_area_sqm"].str.strip()).isna(),
        "resale_price": P.parse_decimal(raw["resale_price"].str.strip()).isna(),
        "lease_commence_date": P.parse_year(raw["lease_commence_date"].str.strip()).isna(),
        "remaining_lease": P.parse_remaining_lease(raw["remaining_lease"].str.strip())["remaining_lease_months"].isna(),
        "storey_range": P.parse_storey_range(raw["storey_range"].str.strip().str.upper())["storey_lower"].isna(),
    }
    rows = []
    for col in EXPECTED_COLUMNS:
        blank = P.is_blank(raw[col])
        fail = parse_fail.get(col)
        rows.append({
            "field": col,
            "blank_count": int(blank.sum()),
            "blank_pct": round(100 * blank.mean(), 4),
            "distinct_values": int(raw[col].nunique()),
            "parse_failures_non_blank": None if fail is None else int((fail & ~blank).sum()),
            "leading_trailing_whitespace": int((raw[col] != raw[col].str.strip()).sum()),
        })
    return rows


def build_report(raw: pd.DataFrame, result: CleanResult, manifest: dict[str, Any],
                 gates: GateResult, previous_manifest: dict[str, Any] | None) -> dict[str, Any]:
    clean = result.clean
    full = clean.loc[~clean["is_partial_month"]]
    monthly = clean.groupby(clean["month_date"].dt.strftime("%Y-%m")).size()
    all_months = pd.period_range(clean["month_date"].min(), clean["month_date"].max(), freq="M")
    missing_months = sorted(set(all_months.strftime("%Y-%m")) - set(monthly.index))

    dup = clean.loc[clean["duplicate_group_size"] > 1]
    dup_groups = dup.groupby(EXPECTED_COLUMNS).size()
    lease = clean["lease_discrepancy_years"].dropna()

    lease_format = raw["remaining_lease"].str.strip().str.replace(r"\d+", "N", regex=True).value_counts()
    lease_format_by_year = (raw.assign(y=raw["month"].str[:4],
                                       f=raw["remaining_lease"].str.replace(r"\d+", "N", regex=True))
                            .groupby(["y", "f"]).size().unstack(fill_value=0))

    return {
        "snapshot": {
            "snapshot_id": manifest["snapshot_id"],
            "dataset_id": manifest["dataset_id"],
            "retrieved_at_local": manifest["retrieved_at_local"],
            "source_last_updated_at": manifest["source_metadata"].get("last_updated_at"),
            "declared_coverage": [manifest["source_metadata"].get("coverage_start"),
                                  manifest["source_metadata"].get("coverage_end")],
            "sha256": manifest["sha256"],
            "previous_snapshot_id": previous_manifest["snapshot_id"] if previous_manifest else None,
            "previous_row_count": previous_manifest["row_count"] if previous_manifest else None,
        },
        "gates": {"passed": gates.passed, "blocking": gates.blocking, "warnings": gates.warnings},
        "counts": {
            "raw_rows": int(len(raw)),
            "manifest_row_count": manifest["row_count"],
            "clean_rows": int(len(clean)),
            "quarantined_rows": int(len(result.quarantine)),
            "partial_month_rows": int(clean["is_partial_month"].sum()),
            "analysis_ready_rows_excl_partial_month": int(len(full)),
        },
        "coverage": {
            "first_month": monthly.index.min(),
            "last_month": monthly.index.max(),
            "months_present": int(len(monthly)),
            "missing_months_in_range": missing_months,
            "partial_months": sorted(clean.loc[clean["is_partial_month"], "month_date"]
                                     .dt.strftime("%Y-%m").unique().tolist()),
            "monthly_rows_min_full_month": int(full.groupby("month_date").size().min()) if len(full) else None,
            "monthly_rows_max_full_month": int(full.groupby("month_date").size().max()) if len(full) else None,
            "monthly_rows": {k: int(v) for k, v in monthly.items()},
        },
        "fields": _field_profile(raw),
        "categories": {
            "town": clean["town"].value_counts().sort_index().to_dict(),
            "flat_type": clean["flat_type"].value_counts().sort_index().to_dict(),
            "flat_model": clean["flat_model"].value_counts().sort_index().to_dict(),
            "storey_range": clean["storey_range"].value_counts().sort_index().to_dict(),
            "new_categories_vs_reference": result.new_categories,
        },
        "numeric_ranges": {
            col: {k: (None if pd.isna(v) else round(float(v), 3)) for k, v in
                  clean[col].astype("float64").describe(percentiles=[.001, .01, .5, .99, .999]).items()}
            for col in ["resale_price_sgd", "floor_area_sqm_num", "price_per_sqm_sgd",
                        "lease_commence_year", "remaining_lease_years", "storey_mid"]
        },
        "remaining_lease": {
            "format_counts": lease_format.to_dict(),
            "format_counts_by_year": {str(y): {k: int(v) for k, v in r.items() if v} for y, r in lease_format_by_year.iterrows()},
            "discrepancy_vs_derived_years": {k: round(float(v), 3) for k, v in
                                             lease.describe(percentiles=[.01, .05, .5, .95, .99]).items()},
            "rows_abs_discrepancy_gt_tolerance": int(clean["flag_lease_inconsistent"].sum()),
        },
        "duplicates": {
            "rows_in_duplicate_groups": int(len(dup)),
            "duplicate_groups": int(len(dup_groups)),
            "excess_rows_if_deduplicated": int(len(dup) - len(dup_groups)),
            "group_size_distribution": {int(k): int(v) for k, v in dup_groups.value_counts().sort_index().items()},
            "by_flat_type": dup["flat_type"].value_counts().to_dict(),
            "by_year": {str(k): int(v) for k, v in dup["year"].value_counts().sort_index().items()},
            "share_price_multiple_of_1000": round(float((dup["resale_price_sgd"] % 1000 == 0).mean()), 4) if len(dup) else None,
            "share_price_multiple_of_1000_all_rows": round(float((clean["resale_price_sgd"] % 1000 == 0).mean()), 4),
        },
        "quarantine": {
            "by_reason": {k: v for k, v in result.rule_counts.items() if k.startswith("Q") and v},
        },
        "rules": result.rule_counts,
    }


def render_markdown(rep: dict[str, Any]) -> str:
    s, c, cov = rep["snapshot"], rep["counts"], rep["coverage"]
    lines = [
        f"# Data Quality Report — snapshot {s['snapshot_id']}",
        "",
        "_Generated automatically by `src/validation/quality_report.py`. Do not edit by hand._",
        "",
        f"- Dataset: `{s['dataset_id']}`; retrieved {s['retrieved_at_local']}; source last updated {s['source_last_updated_at']}",
        f"- SHA-256: `{s['sha256']}`",
        f"- Gates passed: **{rep['gates']['passed']}**; blocking: {rep['gates']['blocking'] or 'none'}; warnings: {rep['gates']['warnings'] or 'none'}",
        "",
        "## Counts",
        "",
        "| Measure | Rows |", "|---|---:|",
        *[f"| {k} | {v:,} |" for k, v in c.items()],
        "",
        "## Coverage",
        "",
        f"- Months: {cov['first_month']} to {cov['last_month']} ({cov['months_present']} months present)",
        f"- Missing months within range: {cov['missing_months_in_range'] or 'none'}",
        f"- Partial (still-accumulating) months: {cov['partial_months'] or 'none'}",
        f"- Rows per full month: min {cov['monthly_rows_min_full_month']:,}, max {cov['monthly_rows_max_full_month']:,}",
        "",
        "## Field profile (raw text)",
        "",
        "| Field | Blank | Blank % | Distinct | Parse failures (non-blank) | Untrimmed |",
        "|---|---:|---:|---:|---:|---:|",
        *[f"| {r['field']} | {r['blank_count']:,} | {r['blank_pct']} | {r['distinct_values']:,} | "
          f"{'n/a' if r['parse_failures_non_blank'] is None else format(r['parse_failures_non_blank'], ',')} | "
          f"{r['leading_trailing_whitespace']:,} |" for r in rep["fields"]],
        "",
        "## Rules and flags (affected rows)",
        "",
        "| Rule / flag | Rows |", "|---|---:|",
        *[f"| {k} | {v:,} |" for k, v in rep["rules"].items()],
        "",
        "## Remaining lease",
        "",
        f"- Formats: {rep['remaining_lease']['format_counts']}",
        f"- Discrepancy (source − derived, years): {rep['remaining_lease']['discrepancy_vs_derived_years']}",
        f"- Rows with |discrepancy| above tolerance: {rep['remaining_lease']['rows_abs_discrepancy_gt_tolerance']:,}",
        "",
        "## Duplicates (identical on all 11 source fields)",
        "",
        *[f"- {k}: {v}" for k, v in rep["duplicates"].items()],
        "",
        "## New categories vs reference sets",
        "",
        f"- {rep['categories']['new_categories_vs_reference']}",
        "",
    ]
    return "\n".join(lines)
