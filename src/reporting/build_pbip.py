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
    Tables import CSVs from the Power Query parameter ``CuratedFolder``. By default it is a
    placeholder (no personal path is committed, DEC-029): set it once in Desktop
    (Transform data > Edit parameters) or regenerate with ``--local-path``.

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
# Committed default (DEC-029): no personal path in the public repository. Users set the
# CuratedFolder parameter once in Desktop, or regenerate with --local-path.
PLACEHOLDER_FOLDER = "C:\\path\\to\\hdb-resale-market-intelligence\\data\\curated\\"


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

SORT_BY = {("dim_flat_type", "flat_type"): "flat_type_order", ("dim_storey_range", "storey_range"): "storey_order",
           ("dim_storey_range", "storey_label"): "storey_order",
           ("storey_effects_adjusted", "level_label"): "level_order",
           ("hypothesis_results", "question"): "hypothesis_order"}
HIDDEN = {("dim_flat_type", "flat_type_order"), ("dim_storey_range", "storey_order"),
          ("storey_effects_adjusted", "level_order"), ("hypothesis_results", "hypothesis_order")}

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
            "IF ( [Transactions Latest 12M] < 30, \"Too few (under 30)\", \"Yes\" )", "", "Latest 12 months",
            "Warns when a comparison rests on fewer than 30 sales (shown as 'Enough sales?')."),
    # --- Context ---
    Measure("refresh_info", "Data Coverage Text",
            "\"Data covers \" & SELECTEDVALUE ( refresh_info[first_month_label] ) & \" to \" & "
            "SELECTEDVALUE ( refresh_info[last_full_month_label] ) & \" (complete months). \" & "
            "SELECTEDVALUE ( refresh_info[partial_month_label] ) & \" is still being recorded and is left out of "
            "trends. Data downloaded \" & SELECTEDVALUE ( refresh_info[retrieved_label] ) & \".\"", "", "Context",
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
            "MAX ( town_effects_adjusted[pct_vs_reference] ) / 100", "0%", "Evidence",
            "Adjusted price difference vs Ang Mo Kio (model M1, recent window)."),
    # --- Model ---
    Measure("model_comparison", "Test MAE", "MAX ( model_comparison[mae] )", SGD, "Model",
            "Mean absolute error on the test year (SGD)."),
    Measure("model_comparison", "Selected Model MAE (Static)",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Chosen model (not updated)\" )",
            SGD, "Model", "Test MAE of the selected model trained once before the test year."),
    Measure("model_comparison", "Selected Model MAE (Monthly Refit)",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Chosen model (updated monthly)\" )",
            SGD, "Model", "Test MAE when retrained before each month."),
    Measure("model_comparison", "Selected Model Typical % Error",
            "CALCULATE ( MAX ( model_comparison[mdape_pct] ), model_comparison[model_label] = "
            "\"Chosen model (not updated)\" ) / 100", PCT1, "Model", "Median absolute % error."),
    Measure("model_comparison", "Selected Model R2",
            "CALCULATE ( MAX ( model_comparison[r2] ), model_comparison[model_label] = "
            "\"Chosen model (not updated)\" )", "0.000", "Model", "R-squared on the test year."),
    Measure("model_comparison", "Baseline B2 MAE",
            "CALCULATE ( [Test MAE], model_comparison[model_label] = \"Simple benchmark (recent typical price)\" )",
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
def col(entity: str, prop: str, label: str | None = None, fmt: str | None = None) -> dict:
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if label:
        p["displayName"] = label
    if fmt:
        p["format"] = fmt
    return p


def meas(entity: str, prop: str, label: str | None = None) -> dict:
    p = {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if label:
        p["displayName"] = label
    return p


def lit(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def color(hex_: str) -> dict:
    return {"solid": {"color": lit(f"'{hex_}'")}}


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
    text_size: str = "10pt"
    bold: bool = False


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
        style = {"fontSize": v.text_size, **({"fontWeight": "bold"} if v.bold else {})}
        visual["objects"] = {"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": line, "textStyle": style}]} for line in v.text.split("\n")]}}]}
    if v.title:
        visual["visualContainerObjects"] = {
            "title": [{"properties": {"show": lit("true"), "text": lit("'" + v.title.replace("'", "''") + "'")}}],
            # Auto-generated subtitles ("X by Y") repeat the title and take space from the chart (review 3).
            "subTitle": [{"properties": {"show": lit("false")}}]}
    visual["drillFilterOtherVisuals"] = True
    return {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/{VERSIONS['visual']}/schema.json",
            "name": name, "position": {"x": v.x, "y": v.y, "z": z, "height": v.h, "width": v.w, "tabOrder": z},
            "visual": visual}


# Visual-review fixes (BI_BUILD_GUIDE §9, review 1): slicers need ~75 px for title + dropdown box with
# the field header hidden; cards need ~120 px with an explicit value font size and no display-unit
# abbreviation; long text goes in a smaller-font card; tables use short display names and formats.
def slicer(entity: str, prop: str, x: int, y: int, w: int = 250, h: int = 75, title: str | None = None) -> Visual:
    return Visual("slicer", x, y, w, h, {"Values": [col(entity, prop)]}, title=title,
                  objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}],
                           "header": [{"properties": {"show": lit("false")}}]})


def card(entity: str, measure: str, x: int, y: int, title: str, w: int = 300, h: int = 120) -> Visual:
    return Visual("card", x, y, w, h, {"Values": [meas(entity, measure)]}, title=title,
                  objects={"labels": [{"properties": {"fontSize": lit("22D"), "labelDisplayUnits": lit("1D")}}],
                           "categoryLabels": [{"properties": {"show": lit("false")}}]})


def text_card(entity: str, measure: str, x: int, y: int, w: int, h: int) -> Visual:
    return Visual("card", x, y, w, h, {"Values": [meas(entity, measure)]},
                  objects={"labels": [{"properties": {"fontSize": lit("10D")}}],
                           "categoryLabels": [{"properties": {"show": lit("false")}}]})


def series_colors(entity: str, colors: dict[str, str]) -> dict:
    """Per-measure series colours (selector by queryRef)."""
    return {"dataPoint": [{"properties": {"fill": color(c)}, "selector": {"metadata": f"{entity}.{m}"}}
                          for m, c in colors.items()]}


F = "fact_transactions"
ORANGE, BLUE, AQUA = "#eb6834", "#2a78d6", "#1baf7a"
SGD_FMT = r"\$#,0"


def _interval_coverage_pct() -> str:
    """Measured coverage of the withheld price ranges, read from the model results (never hard-coded)."""
    res = json.loads((REPO_ROOT / "outputs" / "model_metrics" / "model_results.json").read_text(encoding="utf-8"))
    return f"{100 * res['conformal_80']['coverage_test_static']:.0f}%"


def pages() -> list[tuple[str, str, list[Visual]]]:
    """Report pages. All wording follows docs/DASHBOARD_GLOSSARY.md (plain business language, DEC-030)."""
    header = lambda t: Visual("textbox", 20, 6, 1240, 40, text=t, text_size="14pt", bold=True)  # noqa: E731
    cov = text_card("refresh_info", "Data Coverage Text", 20, 668, 1240, 46)
    p1 = [
        header("Market overview: how are HDB resale prices and sales changing?"),
        slicer("dim_town", "town", 20, 46, 300, 72, "Town"),
        slicer("dim_flat_type", "flat_type", 330, 46, 300, 72, "Flat type"),
        card(F, "Median Price Latest 12M", 20, 124, "Typical price (median), last 12 months"),
        card(F, "Median Price YoY %", 330, 124, "Price change vs previous 12 months"),
        card(F, "Transactions Latest 12M", 640, 124, "Flats sold, last 12 months"),
        card(F, "Median Price per sqm Latest 12M", 950, 124, "Typical price per sqm, last 12 months", w=310),
        Visual("lineChart", 20, 252, 620, 205, {"Category": [col("dim_month", "month", "Month")],
                                                "Y": [meas(F, "Median Price (Full Months)", "Typical price")]},
               title="Typical resale price each month"),
        Visual("clusteredColumnChart", 650, 252, 610, 205, {"Category": [col("dim_month", "month", "Month")],
                                                            "Y": [meas(F, "Transactions (Full Months)", "Flats sold")]},
               title="Flats sold each month"),
        Visual("clusteredColumnChart", 20, 465, 620, 197, {"Category": [col("dim_flat_type", "flat_type", "Flat type")],
                                                           "Y": [meas(F, "Median Price Latest 12M", "Typical price")],
                                                           "Tooltips": [meas(F, "Transactions Latest 12M", "Flats sold")]},
               title="Typical price by flat type, last 12 months (hover for number sold)"),
        Visual("tableEx", 650, 465, 610, 197, {"Values": [col("dim_flat_type", "flat_type", "Flat type"),
                                                          meas(F, "Transactions Latest 12M", "Flats sold"),
                                                          meas(F, "Median Price Latest 12M", "Typical price"),
                                                          meas(F, "Median Price YoY %", "Change vs last year")]},
               title="This year vs last year (changes also reflect which flats were sold)"),
        cov,
    ]
    p2 = [
        header("Compare towns and flats: what do similar flats sell for?"),
        slicer("dim_flat_type", "flat_type", 20, 46, 250, 72, "Flat type"),
        slicer("dim_town", "town", 280, 46, 250, 72, "Town"),
        slicer(F, "floor_area_band", 540, 46, 250, 72, "Flat size (sqm)"),
        Visual("tableEx", 20, 124, 780, 538, {"Values": [col("dim_town", "town", "Town"),
                                                          meas(F, "Transactions Latest 12M", "Flats sold"),
                                                          meas(F, "Median Price Latest 12M", "Typical price"),
                                                          meas(F, "P25 Price Latest 12M", "Low end"),
                                                          meas(F, "P75 Price Latest 12M", "High end"),
                                                          meas(F, "Median Price per sqm Latest 12M", "Price per sqm"),
                                                          meas(F, "Sample Size Flag Latest 12M", "Enough sales?")]},
               title="Prices by town, last 12 months (half of all sales fall between Low end and High end)",
               sort=(meas(F, "Median Price Latest 12M"), "Descending")),
        Visual("clusteredColumnChart", 810, 124, 450, 265, {"Category": [col("dim_storey_range", "storey_label", "Floor level")],
                                                            "Y": [meas(F, "Median Price Latest 12M", "Typical price")],
                                                            "Tooltips": [meas(F, "Transactions Latest 12M", "Flats sold")]},
               title="Typical price by floor level (all towns combined)"),
        Visual("clusteredColumnChart", 810, 397, 450, 265, {"Category": [col(F, "lease_band", "Years of lease left")],
                                                            "Y": [meas(F, "Median Price Latest 12M", "Typical price")],
                                                            "Tooltips": [meas(F, "Transactions Latest 12M", "Flats sold")]},
               title="Typical price by years of lease left"),
        cov,
    ]
    H = "hypothesis_results"
    p3 = [
        header("What drives price differences? Comparing otherwise similar flats"),
        Visual("tableEx", 20, 46, 1240, 240, {"Values": [col(H, "question", "Question"),
                                                          col(H, "finding", "What the data shows"),
                                                          col(H, "size_of_effect", "Size of effect"),
                                                          col(H, "likely_range", "Likely range"),
                                                          col(H, "evidence", "Evidence")]},
               title="Key findings: price differences between flats that are otherwise alike"),
        Visual("lineChart", 20, 294, 305, 302, {"Category": [col("price_index_monthly", "month", "Month")],
                                                "Y": [meas("price_index_monthly", "Raw Median Index", "Headline (all sales)"),
                                                      meas("price_index_monthly", "Mix-Adjusted Index", "Like-for-like flats")]},
               title="Headline vs like-for-like price trend (2017 = 100)",
               objects=series_colors("price_index_monthly", {"Raw Median Index": ORANGE,
                                                             "Mix-Adjusted Index": BLUE})),
        Visual("lineChart", 333, 294, 305, 302, {"Category": [col("storey_effects_adjusted", "level_order", "Floor (lowest floor of band)")],
                                                 "Y": [meas("storey_effects_adjusted", "Storey Premium vs Lowest Band", "Extra paid")]},
               title="Extra paid for higher floors (vs floors 1-3)"),
        Visual("lineChart", 646, 294, 305, 302, {"Category": [col("lease_effects_adjusted", "level_order", "Years of lease left")],
                                                 "Y": [meas("lease_effects_adjusted", "Lease Premium vs Shortest Band", "Extra paid")]},
               title="Extra paid for more lease left (vs 35-39 years)"),
        Visual("clusteredBarChart", 959, 294, 301, 302, {"Category": [col("town_effects_adjusted", "level", "Town")],
                                                         "Y": [meas("town_effects_adjusted", "Town Effect vs Ang Mo Kio", "Price level")]},
               title="Town price level vs Ang Mo Kio (similar flats)",
               sort=(meas("town_effects_adjusted", "Town Effect vs Ang Mo Kio"), "Descending"),
               objects={"valueAxis": [{"properties": {"show": lit("false")}}],
                        "labels": [{"properties": {"show": lit("true")}}]}),
        Visual("textbox", 20, 604, 1240, 66, text=(
            "How to read: each result compares flats that are alike in size, type, design, floor, lease and month of "
            "sale, so the difference shows the effect of the one factor named. Like-for-like trend = price change for "
            "the same kind of flat; the headline trend also moves when a different mix of flats is sold.\n"
            "These are patterns in past sales, not proof of cause: exact location, condition and views also matter. "
            "Results are fixed calculations and do not change with filters. Details: docs/HYPOTHESIS_REGISTER.md.")),
    ]
    MC, ME = "model_comparison", "model_errors_by_month"
    S = "model_segment_errors"
    p4 = [
        header("How accurate are the price estimates, and where are they less reliable?"),
        card(MC, "Selected Model MAE (Static)", 20, 46, "Average prediction error (SGD)", w=240),
        card(MC, "Selected Model Typical % Error", 270, 46, "Typical error (%)", w=240),
        card(MC, "Selected Model MAE (Monthly Refit)", 520, 46, "Average error with monthly updates", w=240),
        card(MC, "Baseline B2 MAE", 770, 46, "Error using a simple benchmark", w=240),
        card(MC, "Error Reduction vs Baseline", 1020, 46, "Reduction in prediction error", w=240),
        Visual("clusteredBarChart", 20, 174, 620, 262, {"Category": [col(MC, "model_label", "Approach")],
                                                        "Y": [meas(MC, "Test MAE", "Average error (SGD)")]},
               title="Prediction accuracy by approach (lower error is better)",
               sort=(meas(MC, "Test MAE"), "Ascending")),
        Visual("lineChart", 650, 174, 610, 262, {"Category": [col(ME, "month", "Month")],
                                                 "Y": [meas(ME, "MAE Trained Once", "Model not updated"),
                                                       meas(ME, "MAE Retrained Monthly", "Model updated monthly"),
                                                       meas(ME, "MAE Baseline B2", "Simple benchmark")]},
               title="Does prediction accuracy worsen over time? (average error by month)",
               objects=series_colors(ME, {"MAE Trained Once": BLUE, "MAE Retrained Monthly": AQUA,
                                          "MAE Baseline B2": ORANGE})),
        slicer(S, "segment_label", 20, 444, 170, 72, "Break down by"),
        # No "Grouping" column: the filter on the left names it, and group names are self-explanatory
        # (review 4: removing it lets the "Reliable?" column fit).
        Visual("tableEx", 198, 444, 722, 218, {"Values": [col(S, "level_label", "Group"),
                                                           col(S, "n", "Sales tested", "#,0"),
                                                           col(S, "mae", "Average error", SGD_FMT),
                                                           col(S, "mdape_pct", "Typical error (%)", "0.0"),
                                                           col(S, "bias_median_pct", "Over/under (%)", "0.0"),
                                                           col(S, "reliability_label", "Reliable?")]},
               title="Where are predictions less accurate? (Over/under: + means estimates too high)"),
        Visual("clusteredBarChart", 928, 444, 332, 218, {"Category": [col("model_feature_importance", "feature_label", "Factor")],
                                                         "Y": [meas("model_feature_importance", "MAE Increase When Shuffled",
                                                                    "Accuracy lost without it")]},
               title="Which factors influence predictions (not necessarily causes)",
               sort=(meas("model_feature_importance", "MAE Increase When Shuffled"), "Descending")),
        Visual("textbox", 20, 668, 1240, 48, text=(
            "How we tested: the model estimated the latest 12 months of sales without seeing them. Average error = the "
            "average gap between estimated and actual price. Typical error (%) = half of all estimates were closer than "
            "this. Price ranges are not shown: in testing they captured only "
            f"{_interval_coverage_pct()} of actual prices instead of the intended 80%. Details: docs/MODEL_CARD.md."),
            text_size="9pt"),
    ]
    PR = "indicative_profiles"
    p5 = [
        header("Estimated prices for typical flats (for guidance only, not a valuation)"),
        slicer("dim_town", "town", 20, 46, 300, 72, "Town"),
        slicer("dim_flat_type", "flat_type", 330, 46, 300, 72, "Flat type"),
        Visual("tableEx", 20, 124, 1240, 470, {"Values": [col(PR, "town", "Town"),
                                                           col(PR, "flat_type", "Flat type"),
                                                           col(PR, "storey_variant", "Floor level"),
                                                           col(PR, "flat_model", "Flat model"),
                                                           col(PR, "floor_area_sqm", "Size (sqm)", "0"),
                                                           col(PR, "remaining_lease_years", "Lease left (years)", "0.0"),
                                                           col(PR, "estimated_price_rounded", "Estimated price", SGD_FMT),
                                                           col(PR, "typical_error_pct", "Typical error (%)", "0.0"),
                                                           col(PR, "typical_error_sgd", "Typical error (SGD)", SGD_FMT),
                                                           col(PR, "segment_median_price_latest_12m", "Recent typical price", SGD_FMT),
                                                           col(PR, "reliability", "Reliability")]},
               title="Estimated price of a typical flat in each town and flat type, at three floor levels"),
        Visual("textbox", 20, 602, 1240, 110, text=(
            "How to read: each row describes a typical flat sold in that town (usual size, lease, design and street). "
            "Estimated price = the model's estimate for the latest complete month. Typical error = how far off estimates "
            "usually were for this town and flat type when tested. Recent typical price = the actual median price of "
            "all such flats sold in the last 12 months.\n"
            "Estimates were calculated in advance: filters only narrow the list, they do not recalculate prices. "
            "For guidance only: not a valuation, not the price of a specific flat, and not for loan or negotiation "
            "decisions.")),
    ]
    return [("p1_overview", "1 Market overview", p1), ("p2_compare", "2 Compare towns & flats", p2),
            ("p3_evidence", "3 What drives prices", p3), ("p4_model", "4 Estimate accuracy", p4),
            ("p5_estimates", "5 Estimated prices", p5)]


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
    ap.add_argument("--local-path", action="store_true",
                    help="write this machine's data/curated path (for local validation only; do not commit)")
    args = ap.parse_args(argv)
    cfg = load_config()
    curated = cfg.curated_dir
    if args.curated_folder:
        folder = args.curated_folder
    elif args.local_path:
        folder = str(curated.resolve()) + "\\"
    else:
        folder = PLACEHOLDER_FOLDER
    root = REPO_ROOT / "powerbi"
    # Remove previously generated files (not folders: Power BI Desktop locks the folders of an
    # open project, but regenerating while it is open is still useful). Empty folders that are
    # no longer generated are removed when possible.
    for sub in [f"{PROJECT}.SemanticModel", f"{PROJECT}.Report"]:
        if (root / sub).exists():
            for f in sorted((root / sub).rglob("*"), reverse=True):
                if f.is_file() and ".pbi" not in f.parts:
                    f.unlink()
                elif f.is_dir():
                    try:
                        f.rmdir()
                    except OSError:
                        pass
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
