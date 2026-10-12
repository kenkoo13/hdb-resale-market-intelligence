"""Generate the Power BI Project (PBIP) from a single Python specification (Phase 4).

Usage
    python -m src.reporting.build_pbip [--curated-folder "D:/path/to/data/curated/"]

Output
    powerbi/HDB Resale Market.pbip
    powerbi/HDB Resale Market.SemanticModel/   TMDL semantic model (tables, relationships, DAX)
    powerbi/HDB Resale Market.Report/          PBIR report (5 pages)

Why generate instead of hand-building in Desktop
    * The model, measures and visuals are reviewable text under version control.
    * Re-running after a data refresh or a measure change reproduces the project exactly.
    * Every DAX measure is defined once here and documented in docs/BI_BUILD_GUIDE.md.

Data connection
    Tables import CSVs from the Power Query parameter ``CuratedFolder``. It is set to
    this repository's data/curated folder at generation time; another user changes it
    in Desktop (Transform data > Edit parameters) or re-runs this script.

Formats follow Microsoft's published JSON schemas (PBIR report 3.0.0, page 2.0.0,
visualContainer 2.4.0) and TMDL. Validity is checked by (1) parsing the TMDL with
Power BI's own TMDL serializer and (2) opening the project in Power BI Desktop and
querying its engine (docs/BI_BUILD_GUIDE.md §7).
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import REPO_ROOT, load_config

PROJECT = "HDB Resale Market"
NS = uuid.UUID("6f1c2d3e-0000-4000-8000-000000000001")  # namespace for stable lineage tags
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
BASE_THEME = "Fluent2-CY26SU09"
THEME_SRC = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\WebView2Resources\minerva"
                 r"\sharedresources\BaseThemes") / f"{BASE_THEME}.json"
VERSIONS = {"visual": "2.4.0", "page": "2.0.0", "report": "3.0.0"}
PAGE_W, PAGE_H = 1280, 720


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


# --------------------------------------------------------------------------------------
# Semantic model specification
# --------------------------------------------------------------------------------------
TABLES = [  # (table name, csv file, columns forced to date)
    ("fact_transactions", "fact_transactions.csv", ["month"]),
    ("dim_month", "dim_month.csv", ["month"]),
    ("dim_town", "dim_town.csv", []),
    ("dim_flat_type", "dim_flat_type.csv", []),
    ("dim_storey_range", "dim_storey_range.csv", []),
    ("dim_flat_model", "dim_flat_model.csv", []),
    ("price_index_monthly", "price_index_monthly.csv", ["month"]),
    ("hypothesis_results", "hypothesis_results.csv", []),
    ("storey_effects_adjusted", "storey_effects_adjusted.csv", []),
    ("lease_effects_adjusted", "lease_effects_adjusted.csv", []),
    ("town_effects_adjusted", "town_effects_adjusted.csv", []),
    ("model_comparison", "model_comparison.csv", []),
    ("model_errors_by_month", "model_errors_by_month.csv", ["month"]),
    ("model_segment_errors", "model_segment_errors.csv", []),
    ("model_feature_importance", "model_feature_importance.csv", []),
    ("indicative_profiles", "indicative_profiles.csv", []),
    ("refresh_info", "refresh_info.csv", []),
]

SORT_BY = {("dim_flat_type", "flat_type"): "flat_type_order", ("dim_storey_range", "storey_range"): "storey_order"}
HIDDEN = {("dim_flat_type", "flat_type_order"), ("dim_storey_range", "storey_order")}

RELATIONSHIPS = [  # (from table.column, to table.column)  many-to-one, single direction
    ("fact_transactions.month", "dim_month.month"),
    ("fact_transactions.town", "dim_town.town"),
    ("fact_transactions.flat_type", "dim_flat_type.flat_type"),
    ("fact_transactions.storey_range", "dim_storey_range.storey_range"),
    ("fact_transactions.flat_model", "dim_flat_model.flat_model"),
    ("price_index_monthly.month", "dim_month.month"),
    ("model_errors_by_month.month", "dim_month.month"),
    ("indicative_profiles.town", "dim_town.town"),
    ("indicative_profiles.flat_type", "dim_flat_type.flat_type"),
]

SGD = r"\$#,0"
PCT1 = "0.0%"


@dataclass
class Measure:
    table: str
    name: str
    dax: str
    fmt: str
    folder: str
    description: str


MEASURES = [
    # --- Market (fact_transactions) ---
    Measure("fact_transactions", "Transactions", "COUNTROWS ( fact_transactions )", "#,0", "Market",
            "Number of registered resale transactions in the current filter context (includes the partial month)."),
    Measure("fact_transactions", "Transactions (Full Months)",
            "CALCULATE ( [Transactions], dim_month[is_partial_month] = 0 )", "#,0", "Market",
            "Transactions excluding the still-accumulating latest month (DEC-008)."),
    Measure("fact_transactions", "Median Price", "MEDIAN ( fact_transactions[resale_price] )", SGD, "Market",
            "Median registered resale price (SGD)."),
    Measure("fact_transactions", "Median Price (Full Months)",
            "CALCULATE ( [Median Price], dim_month[is_partial_month] = 0 )", SGD, "Market",
            "Median price excluding the partial month; used for trends."),
    Measure("fact_transactions", "Mean Price", "AVERAGE ( fact_transactions[resale_price] )", SGD, "Market",
            "Arithmetic mean price; shown for comparison only (skewed upward)."),
    Measure("fact_transactions", "P25 Price", "PERCENTILE.INC ( fact_transactions[resale_price], 0.25 )", SGD,
            "Market", "25th percentile price (linear interpolation, same as pandas quantile)."),
    Measure("fact_transactions", "P75 Price", "PERCENTILE.INC ( fact_transactions[resale_price], 0.75 )", SGD,
            "Market", "75th percentile price."),
    Measure("fact_transactions", "Median Price per sqm", "MEDIAN ( fact_transactions[price_per_sqm] )", SGD,
            "Market", "Median of row-level price per square metre (SGD/sqm)."),
    Measure("fact_transactions", "Median Floor Area", "MEDIAN ( fact_transactions[floor_area_sqm] )", "#,0",
            "Market", "Median floor area (sqm)."),
    Measure("fact_transactions", "Transactions Latest 12M",
            "CALCULATE ( [Transactions], dim_month[is_latest_12m] = 1 )", "#,0", "Latest 12 months",
            "Transactions in the 12 full months ending at the last full month."),
    Measure("fact_transactions", "Median Price Latest 12M",
            "CALCULATE ( [Median Price], dim_month[is_latest_12m] = 1 )", SGD, "Latest 12 months",
            "Median price over the latest 12 full months."),
    Measure("fact_transactions", "Median Price Prior 12M",
            "CALCULATE ( [Median Price], dim_month[is_prior_12m] = 1 )", SGD, "Latest 12 months",
            "Median price over the 12 months before the latest 12."),
    Measure("fact_transactions", "Median Price YoY %",
            "VAR cur = [Median Price Latest 12M] VAR prev = [Median Price Prior 12M] "
            "RETURN IF ( NOT ISBLANK ( cur ) && NOT ISBLANK ( prev ), DIVIDE ( cur, prev ) - 1 )", PCT1,
            "Latest 12 months", "Change in median price, latest 12 vs prior 12 full months. Raw median: "
            "includes changes in the mix of flats sold."),
    Measure("fact_transactions", "P25 Price Latest 12M",
            "CALCULATE ( [P25 Price], dim_month[is_latest_12m] = 1 )", SGD, "Latest 12 months", "25th percentile."),
    Measure("fact_transactions", "P75 Price Latest 12M",
            "CALCULATE ( [P75 Price], dim_month[is_latest_12m] = 1 )", SGD, "Latest 12 months", "75th percentile."),
    Measure("fact_transactions", "Mean Price Latest 12M",
            "CALCULATE ( [Mean Price], dim_month[is_latest_12m] = 1 )", SGD, "Latest 12 months", "Mean price."),
    Measure("fact_transactions", "Median Price per sqm Latest 12M",
            "CALCULATE ( [Median Price per sqm], dim_month[is_latest_12m] = 1 )", SGD, "Latest 12 months",
            "Median SGD per sqm."),
    Measure("fact_transactions", "Sample Size Flag Latest 12M",
            "IF ( [Transactions Latest 12M] < 30, \"Low sample (n<30)\", \"OK\" )", "", "Latest 12 months",
            "Warns when a comparison rests on fewer than 30 sales."),
    # --- Context ---
    Measure("refresh_info", "Data Coverage Text",
            "\"Data: \" & SELECTEDVALUE ( refresh_info[first_month] ) & \" to \" & "
            "SELECTEDVALUE ( refresh_info[last_full_month] ) & \" (full months). Partial month excluded from "
            "trends: \" & SELECTEDVALUE ( refresh_info[partial_month] ) & \". Retrieved \" & "
            "SELECTEDVALUE ( refresh_info[retrieved_at_local] ) & \" SGT.\"", "", "Context",
            "Coverage and refresh timestamp for report headers."),
    Measure("refresh_info", "Attribution Text", "SELECTEDVALUE ( refresh_info[attribution] )", "", "Context",
            "Data licence attribution (Singapore Open Data Licence v1.0)."),
    # --- Analysis results ---
    Measure("price_index_monthly", "Raw Median Index", "MAX ( price_index_monthly[raw_median_index] )", "0.0",
            "Index", "Raw monthly median price, 2017 = 100 (all flats; not affected by town/type slicers)."),
    Measure("price_index_monthly", "Mix-Adjusted Index", "MAX ( price_index_monthly[mix_adjusted_index] )", "0.0",
            "Index", "Hedonic time-dummy index for comparable flats, 2017 = 100 (DEC-017)."),
    Measure("storey_effects_adjusted", "Storey Premium vs Lowest Band",
            "MAX ( storey_effects_adjusted[pct_vs_reference] ) / 100", PCT1, "Evidence",
            "Adjusted price difference vs floors 01-03 (model M2, recent window)."),
    Measure("lease_effects_adjusted", "Lease Premium vs Shortest Band",
            "MAX ( lease_effects_adjusted[pct_vs_reference] ) / 100", PCT1, "Evidence",
            "Adjusted price difference vs the shortest remaining-lease band (model M2)."),
    Measure("town_effects_adjusted", "Town Effect vs Ang Mo Kio",
            "MAX ( town_effects_adjusted[pct_vs_reference] ) / 100", PCT1, "Evidence",
            "Adjusted price difference vs Ang Mo Kio (model M1, recent window)."),
    # --- Model ---
    Measure("model_comparison", "Test MAE", "MAX ( model_comparison[mae] )", SGD, "Model",
            "Mean absolute error on the test year (SGD)."),
    Measure("model_comparison", "Selected Model MAE (Static)",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Selected: gradient boosting (trained once)\" )",
            SGD, "Model", "Test MAE of the selected model trained once before the test year."),
    Measure("model_comparison", "Selected Model MAE (Monthly Refit)",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Selected: gradient boosting (retrained monthly)\" )",
            SGD, "Model", "Test MAE when retrained before each month."),
    Measure("model_comparison", "Selected Model Typical % Error",
            "CALCULATE ( MAX ( model_comparison[mdape_pct] ), model_comparison[model_label] = "
            "\"Selected: gradient boosting (trained once)\" ) / 100", PCT1, "Model", "Median absolute % error."),
    Measure("model_comparison", "Selected Model R2",
            "CALCULATE ( MAX ( model_comparison[r2] ), model_comparison[model_label] = "
            "\"Selected: gradient boosting (trained once)\" )", "0.000", "Model", "R-squared on the test year."),
    Measure("model_comparison", "Baseline B2 MAE",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Baseline B2: town x type median, last 12 months\" )",
            SGD, "Model", "Realistic baseline MAE."),
    Measure("model_comparison", "Error Reduction vs Baseline",
            "DIVIDE ( [Baseline B2 MAE] - [Selected Model MAE (Static)], [Baseline B2 MAE] )", PCT1, "Model",
            "Share of baseline error removed by the selected model."),
    Measure("model_errors_by_month", "MAE Trained Once", "MAX ( model_errors_by_month[mae_static] )", SGD,
            "Model", "Test MAE by month, model trained once."),
    Measure("model_errors_by_month", "MAE Retrained Monthly", "MAX ( model_errors_by_month[mae_monthly_refit] )",
            SGD, "Model", "Test MAE by month, model retrained monthly."),
    Measure("model_errors_by_month", "MAE Baseline B2", "MAX ( model_errors_by_month[mae_B2_monthly_refit] )",
            SGD, "Model", "Test MAE by month, baseline B2 (monthly refit)."),
    Measure("model_feature_importance", "MAE Increase When Shuffled",
            "MAX ( model_feature_importance[mae_increase_sgd] )", SGD, "Model", "Permutation importance (SGD)."),
    Measure("indicative_profiles", "Profile Estimate", "MAX ( indicative_profiles[estimated_price_rounded] )", SGD,
            "Estimates", "Indicative estimate for a defined profile (pre-computed in Python; not live)."),
]


# --------------------------------------------------------------------------------------
# TMDL writer
# --------------------------------------------------------------------------------------
def _tmdl_type(dtype) -> tuple[str, str]:
    """pandas dtype -> (TMDL dataType, Power Query type)."""
    if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype):
        return "string", "type text"
    if pd.api.types.is_integer_dtype(dtype):
        return "int64", "Int64.Type"
    return "double", "type number"


def _q(name: str) -> str:
    return f"'{name}'" if any(c in name for c in " -.()%/'") else name


def column_types(curated: Path, csv: str, date_cols: list[str]) -> list[tuple[str, str, str]]:
    sample = pd.read_csv(curated / csv, nrows=5000)
    out = []
    for col in sample.columns:
        if col in date_cols:
            out.append((col, "dateTime", "type date"))
        else:
            out.append((col, *_tmdl_type(sample[col].dtype)))
    return out


def table_tmdl(name: str, csv: str, cols: list[tuple[str, str, str]]) -> str:
    lines = [f"table {name}", f"\tlineageTag: {tag('table', name)}", ""]
    for m in [m for m in MEASURES if m.table == name]:
        # TMDL stores descriptions as /// comments directly above the object.
        lines += [f"\t/// {m.description}", f"\tmeasure {_q(m.name)} = {m.dax}"]
        if m.fmt:
            lines += [f"\t\tformatString: {m.fmt}"]
        lines += [f"\t\tdisplayFolder: {m.folder}", f"\t\tlineageTag: {tag('measure', name, m.name)}", ""]
    for col, dtype, _ in cols:
        lines += [f"\tcolumn {_q(col)}", f"\t\tdataType: {dtype}"]
        if dtype == "dateTime":
            lines += ["\t\tformatString: yyyy-mm"]
        lines += [f"\t\tlineageTag: {tag('column', name, col)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {col}"]
        if (name, col) in SORT_BY:
            lines += [f"\t\tsortByColumn: {SORT_BY[(name, col)]}"]
        if (name, col) in HIDDEN:
            lines += ["\t\tisHidden"]
        lines += [""]
    types = ", ".join(f'{{"{c}", {pq}}}' for c, _, pq in cols)
    m_lines = [
        "let",
        f'    Source = Csv.Document(File.Contents(CuratedFolder & "{csv}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    lines += [f"\t\t\t\t{l}" for l in m_lines]
    lines += [""]
    return "\n".join(lines) + "\n"


def write_semantic_model(root: Path, curated: Path, folder_param: str) -> list[str]:
    sm = root / f"{PROJECT}.SemanticModel"
    d = sm / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (sm / "definition.pbism").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {}}, indent=2), encoding="utf-8")
    (sm / ".platform").write_text(json.dumps({
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId": tag("logical", "semanticmodel")}}, indent=2), encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n\n", encoding="utf-8")
    names = [t for t, _, _ in TABLES]
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
             "", "annotation __PBI_TimeIntelligenceEnabled = 0", "",
             "annotation PBI_QueryOrder = " + json.dumps(["CuratedFolder", *names]), ""]
    model += [f"ref table {n}" for n in names] + [""]
    (d / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    (d / "expressions.tmdl").write_text(
        f'expression CuratedFolder = "{folder_param}" meta [IsParameterQuery = true, Type = "Text", '
        f'IsParameterQueryRequired = true]\n\tlineageTag: {tag("expr", "CuratedFolder")}\n\n'
        "\tannotation PBI_ResultType = Text\n\n", encoding="utf-8")
    for name, csv, dates in TABLES:
        cols = column_types(curated, csv, dates)
        (d / "tables" / f"{name}.tmdl").write_text(table_tmdl(name, csv, cols), encoding="utf-8")
    rel = []
    for f, t in RELATIONSHIPS:
        rel += [f"relationship {tag('rel', f, t)}", f"\tfromColumn: {f}", f"\ttoColumn: {t}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")
    return names


# --------------------------------------------------------------------------------------
# PBIR report writer
# --------------------------------------------------------------------------------------
def col(entity: str, prop: str) -> dict:
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def meas(entity: str, prop: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def lit(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


@dataclass
class Visual:
    vtype: str
    x: int
    y: int
    w: int
    h: int
    roles: dict[str, list[dict]] = field(default_factory=dict)
    title: str | None = None
    sort: tuple[dict, str] | None = None  # (projection, "Ascending"/"Descending")
    objects: dict | None = None
    text: str | None = None  # for textboxes


def visual_json(v: Visual, name: str, z: int) -> dict:
    visual: dict = {"visualType": v.vtype}
    if v.roles:
        visual["query"] = {"queryState": {r: {"projections": p} for r, p in v.roles.items()}}
        if v.sort:
            visual["query"]["sortDefinition"] = {"sort": [{"field": v.sort[0]["field"], "direction": v.sort[1]}],
                                                 "isDefaultSort": True}
    if v.objects:
        visual["objects"] = v.objects
    if v.vtype == "textbox":
        visual["objects"] = {"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": line, "textStyle": {"fontSize": "10pt"}}]} for line in v.text.split("\n")]}}]}
    if v.title:
        visual["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"),
                                                                       "text": lit("'" + v.title.replace("'", "''") + "'")}}]}
    visual["drillFilterOtherVisuals"] = True
    return {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/{VERSIONS['visual']}/schema.json",
            "name": name, "position": {"x": v.x, "y": v.y, "z": z, "height": v.h, "width": v.w, "tabOrder": z},
            "visual": visual}


def slicer(entity: str, prop: str, x: int, y: int, w: int = 200, h: int = 60, title: str | None = None) -> Visual:
    return Visual("slicer", x, y, w, h, {"Values": [col(entity, prop)]}, title=title,
                  objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}]})


def card(entity: str, measure: str, x: int, y: int, title: str, w: int = 230, h: int = 100) -> Visual:
    return Visual("card", x, y, w, h, {"Values": [meas(entity, measure)]}, title=title)


F = "fact_transactions"


def pages() -> list[tuple[str, str, list[Visual]]]:
    header = lambda t: Visual("textbox", 20, 8, 1240, 40, text=t)  # noqa: E731
    cov = Visual("card", 20, 650, 1240, 60, {"Values": [meas("refresh_info", "Data Coverage Text")]})
    p1 = [
        header("Executive market overview - HDB resale prices and volumes (indicative, not official valuations)"),
        card(F, "Median Price Latest 12M", 20, 55, "Median price, latest 12 full months"),
        card(F, "Median Price YoY %", 260, 55, "Change vs prior 12 months (raw median)"),
        card(F, "Transactions Latest 12M", 500, 55, "Transactions, latest 12 full months"),
        card(F, "Median Price per sqm Latest 12M", 740, 55, "Median SGD per sqm, latest 12 months"),
        slicer("dim_town", "town", 990, 55, 270, 48, "Town"),
        slicer("dim_flat_type", "flat_type", 990, 105, 270, 48, "Flat type"),
        Visual("lineChart", 20, 165, 620, 235, {"Category": [col("dim_month", "month")],
                                                "Y": [meas(F, "Median Price (Full Months)")]},
               title="Median resale price by month (full months)"),
        Visual("clusteredColumnChart", 650, 165, 610, 235, {"Category": [col("dim_month", "month")],
                                                            "Y": [meas(F, "Transactions (Full Months)")]},
               title="Transactions per month (full months; partial month excluded)"),
        Visual("clusteredBarChart", 20, 410, 620, 230, {"Category": [col("dim_flat_type", "flat_type")],
                                                        "Y": [meas(F, "Median Price Latest 12M")],
                                                        "Tooltips": [meas(F, "Transactions Latest 12M")]},
               title="Median price by flat type, latest 12 months (hover for n)"),
        Visual("tableEx", 650, 410, 610, 230, {"Values": [col("dim_flat_type", "flat_type"),
                                                          meas(F, "Transactions Latest 12M"),
                                                          meas(F, "Median Price Latest 12M"),
                                                          meas(F, "Median Price Prior 12M"),
                                                          meas(F, "Median Price YoY %")]},
               title="Latest vs prior 12 months by flat type (raw medians include mix changes)"),
        cov,
    ]
    p2 = [
        header("Town and property comparison - compare like with like, always check the sample size"),
        slicer("dim_flat_type", "flat_type", 20, 55, 250, 55, "Flat type"),
        slicer("dim_town", "town", 280, 55, 250, 55, "Town"),
        slicer("fact_transactions", "floor_area_band", 540, 55, 250, 55, "Floor area band (sqm)"),
        Visual("tableEx", 20, 120, 640, 520, {"Values": [col("dim_town", "town"), meas(F, "Transactions Latest 12M"),
                                                          meas(F, "Median Price Latest 12M"),
                                                          meas(F, "P25 Price Latest 12M"),
                                                          meas(F, "P75 Price Latest 12M"),
                                                          meas(F, "Median Price per sqm Latest 12M"),
                                                          meas(F, "Sample Size Flag Latest 12M")]},
               title="By town, latest 12 full months (P25-P75 = middle half of prices)",
               sort=(meas(F, "Median Price Latest 12M"), "Descending")),
        Visual("clusteredColumnChart", 670, 120, 590, 255, {"Category": [col("dim_storey_range", "storey_range")],
                                                            "Y": [meas(F, "Median Price Latest 12M")],
                                                            "Tooltips": [meas(F, "Transactions Latest 12M")]},
               title="Median price by storey range (raw; mixes towns - see Evidence page)"),
        Visual("clusteredColumnChart", 670, 385, 590, 255, {"Category": [col(F, "lease_band")],
                                                            "Y": [meas(F, "Median Price Latest 12M")],
                                                            "Tooltips": [meas(F, "Transactions Latest 12M")]},
               title="Median price by remaining lease (years, raw)"),
        cov,
    ]
    p3 = [
        header("Price drivers and statistical evidence - associations in observational data, not causes"),
        Visual("tableEx", 20, 55, 760, 220, {"Values": [col("hypothesis_results", "hypothesis"),
                                                         col("hypothesis_results", "plain_english"),
                                                         col("hypothesis_results", "contrast"),
                                                         col("hypothesis_results", "estimate_pct"),
                                                         col("hypothesis_results", "ci_low_pct"),
                                                         col("hypothesis_results", "ci_high_pct"),
                                                         col("hypothesis_results", "status")]},
               title="Pre-registered hypotheses (estimate % per stated contrast; H5 in percentage points)"),
        Visual("lineChart", 790, 55, 470, 220, {"Category": [col("price_index_monthly", "month")],
                                                "Y": [meas("price_index_monthly", "Raw Median Index"),
                                                      meas("price_index_monthly", "Mix-Adjusted Index")]},
               title="Raw median vs mix-adjusted index (2017 = 100, all flats)"),
        Visual("lineChart", 20, 285, 400, 355, {"Category": [col("storey_effects_adjusted", "level")],
                                                "Y": [meas("storey_effects_adjusted", "Storey Premium vs Lowest Band")]},
               title="Adjusted storey premium vs floors 01-03"),
        Visual("lineChart", 430, 285, 400, 355, {"Category": [col("lease_effects_adjusted", "level")],
                                                 "Y": [meas("lease_effects_adjusted", "Lease Premium vs Shortest Band")]},
               title="Adjusted lease premium vs 35-39 years left"),
        Visual("clusteredBarChart", 840, 285, 420, 355, {"Category": [col("town_effects_adjusted", "level")],
                                                         "Y": [meas("town_effects_adjusted", "Town Effect vs Ang Mo Kio")]},
               title="Adjusted town effect vs Ang Mo Kio (like-for-like)",
               sort=(meas("town_effects_adjusted", "Town Effect vs Ang Mo Kio"), "Descending")),
        Visual("textbox", 20, 650, 1240, 60, text=(
            "Adjusted = hedonic regression holding month, town, flat type, model, floor area, storey and lease fixed. "
            "These tables are pre-computed for the recent window and are not affected by slicers.\n"
            "Unobserved factors (exact location, condition, view) can confound every estimate. "
            "Details: docs/HYPOTHESIS_REGISTER.md.")),
    ]
    p4 = [
        header("Model performance and reliability - test year evaluated once; estimates are indicative"),
        card("model_comparison", "Selected Model MAE (Static)", 20, 55, "Selected model MAE (trained once)"),
        card("model_comparison", "Selected Model Typical % Error", 260, 55, "Typical % error (median)"),
        card("model_comparison", "Selected Model MAE (Monthly Refit)", 500, 55, "MAE if retrained monthly"),
        card("model_comparison", "Baseline B2 MAE", 740, 55, "Baseline MAE (town x type, 12 months)"),
        card("model_comparison", "Error Reduction vs Baseline", 980, 55, "Error removed vs baseline", w=280),
        Visual("clusteredBarChart", 20, 165, 620, 240, {"Category": [col("model_comparison", "model_label")],
                                                        "Y": [meas("model_comparison", "Test MAE")]},
               title="Test-year MAE by model (SGD, lower is better)",
               sort=(meas("model_comparison", "Test MAE"), "Ascending")),
        Visual("lineChart", 650, 165, 610, 240, {"Category": [col("model_errors_by_month", "month")],
                                                 "Y": [meas("model_errors_by_month", "MAE Trained Once"),
                                                       meas("model_errors_by_month", "MAE Retrained Monthly"),
                                                       meas("model_errors_by_month", "MAE Baseline B2")]},
               title="Does accuracy fade? Test MAE by month"),
        slicer("model_segment_errors", "segment", 20, 415, 200, 55, "Segment"),
        Visual("tableEx", 230, 415, 640, 225, {"Values": [col("model_segment_errors", "level"),
                                                           col("model_segment_errors", "n"),
                                                           col("model_segment_errors", "mae"),
                                                           col("model_segment_errors", "mdape_pct"),
                                                           col("model_segment_errors", "bias_median_pct"),
                                                           col("model_segment_errors", "reliability")]},
               title="Errors by segment (mdape = typical % error; bias + = over-estimate)"),
        Visual("clusteredBarChart", 880, 415, 380, 225, {"Category": [col("model_feature_importance", "feature")],
                                                         "Y": [meas("model_feature_importance", "MAE Increase When Shuffled")]},
               title="What the model relies on (not causes)",
               sort=(meas("model_feature_importance", "MAE Increase When Shuffled"), "Descending")),
        Visual("textbox", 20, 650, 1240, 60, text=(
            "Test year: the last 12 full months, never used for model choices. 80% prediction intervals failed their "
            "coverage check (65% actual) and are deliberately not shown.\n"
            "Rare flat types/models, central mature towns and new streets are less reliable. See docs/MODEL_CARD.md.")),
    ]
    p5 = [
        header("Indicative price estimates for typical flat profiles - pre-computed, not a valuation"),
        slicer("dim_town", "town", 20, 55, 300, 55, "Town"),
        slicer("dim_flat_type", "flat_type", 330, 55, 300, 55, "Flat type"),
        Visual("tableEx", 20, 120, 1240, 470, {"Values": [col("indicative_profiles", "town"),
                                                           col("indicative_profiles", "flat_type"),
                                                           col("indicative_profiles", "storey_variant"),
                                                           col("indicative_profiles", "flat_model"),
                                                           col("indicative_profiles", "floor_area_sqm"),
                                                           col("indicative_profiles", "remaining_lease_years"),
                                                           col("indicative_profiles", "estimated_price_rounded"),
                                                           col("indicative_profiles", "typical_error_pct"),
                                                           col("indicative_profiles", "typical_error_sgd"),
                                                           col("indicative_profiles", "segment_median_price_latest_12m"),
                                                           col("indicative_profiles", "reliability")]},
               title="Profiles: segment-typical area, lease, model and street; three storey levels"),
        Visual("textbox", 20, 600, 1240, 110, text=(
            "How to read: each row is a typical flat for that town and flat type, estimated by the selected model "
            "for the last full month. Estimates were computed in Python in advance - changing a slicer filters the "
            "table, it does not re-run the model.\n"
            "Typical error = the larger of the town and flat-type median % error measured on the test year. "
            "Indicative only: not a valuation, not the price of any specific unit, and not suitable for loan "
            "or negotiation decisions.")),
    ]
    return [("p1_overview", "1 Market overview", p1), ("p2_compare", "2 Town & property", p2),
            ("p3_evidence", "3 Price drivers & evidence", p3), ("p4_model", "4 Model performance", p4),
            ("p5_estimates", "5 Indicative estimates", p5)]


def write_report(root: Path) -> int:
    rp = root / f"{PROJECT}.Report"
    d = rp / "definition"
    (d / "pages").mkdir(parents=True, exist_ok=True)
    (rp / "definition.pbir").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}}}, indent=2), encoding="utf-8")
    (rp / ".platform").write_text(json.dumps({
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJECT},
        "config": {"version": "2.0", "logicalId": tag("logical", "report")}}, indent=2), encoding="utf-8")
    (d / "version.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
        indent=2), encoding="utf-8")
    (d / "report.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/report/{VERSIONS['report']}/schema.json",
        "themeCollection": {"baseTheme": {"name": BASE_THEME, "reportVersionAtImport": VERSIONS,
                                          "type": "SharedResources"}}}, indent=2), encoding="utf-8")
    theme_dir = rp / "StaticResources" / "SharedResources" / "BaseThemes"
    theme_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(THEME_SRC, theme_dir / f"{BASE_THEME}.json")
    page_list = pages()
    (d / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p for p, _, _ in page_list], "activePageName": page_list[0][0]}, indent=2), encoding="utf-8")
    n_visuals = 0
    for pid, display, visuals in page_list:
        pd_ = d / "pages" / pid
        (pd_ / "visuals").mkdir(parents=True, exist_ok=True)
        (pd_ / "page.json").write_text(json.dumps({
            "$schema": f"{SCHEMA}/item/report/definition/page/{VERSIONS['page']}/schema.json",
            "name": pid, "displayName": display, "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W}, indent=2), encoding="utf-8")
        for i, v in enumerate(visuals):
            vid = f"{pid}_v{i:02d}"
            (pd_ / "visuals" / vid).mkdir(exist_ok=True)
            (pd_ / "visuals" / vid / "visual.json").write_text(json.dumps(visual_json(v, vid, i), indent=2),
                                                                encoding="utf-8")
            n_visuals += 1
    return n_visuals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated-folder", default=None, help="absolute folder with the curated CSVs (trailing slash)")
    args = ap.parse_args(argv)
    cfg = load_config()
    curated = cfg.curated_dir
    folder = args.curated_folder or (str(curated.resolve()) + "\\")
    root = REPO_ROOT / "powerbi"
    for sub in [f"{PROJECT}.SemanticModel", f"{PROJECT}.Report"]:
        if (root / sub).exists():
            shutil.rmtree(root / sub)
    root.mkdir(exist_ok=True)
    (root / f"{PROJECT}.pbip").write_text(json.dumps({
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
        "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}], "settings": {"enableAutoRecovery": True}},
        indent=2), encoding="utf-8")
    tables = write_semantic_model(root, curated, folder)
    n = write_report(root)
    print(f"PBIP written to {root}: {len(tables)} tables, {len(MEASURES)} measures, {len(RELATIONSHIPS)} "
          f"relationships, {len(pages())} pages, {n} visuals; CuratedFolder = {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
