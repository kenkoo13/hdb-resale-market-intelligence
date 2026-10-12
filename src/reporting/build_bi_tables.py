"""Build the Power BI import tables in data/curated/ (Phase 4).

Usage
    python -m src.reporting.build_bi_tables

Steps
    1. Load the cleaned transactions into an in-memory SQLite database and run
       sql/01_fact_and_dimensions.sql and sql/02_aggregates.sql (star schema + checks).
    2. Cross-check SQL aggregates against pandas (counts and medians must match
       exactly); abort if they do not.
    3. Export star-schema tables and copy the analysis/model result tables the
       report uses, with stable column names.
    4. Compute indicative profile estimates (src/modelling/profiles.py).
    5. Compute expected values for DAX validation (dax_expected_values.csv).

Outputs (data/curated/)
    fact_transactions.csv           ~242k rows (git-ignored; regenerated)
    dim_*.csv, refresh_info.csv     small (committed)
    *_results / model_* / index     small (committed)
    indicative_profiles.csv         small (committed)
    dax_expected_values.csv         small (committed)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.common import analysis_ready, load_clean
from src.config import REPO_ROOT, load_config
from src.modelling.features import add_time_index
from src.modelling.profiles import estimate_profiles

log = logging.getLogger("bi")
SQL_DIR = REPO_ROOT / "sql"
STAR_TABLES = ["fact_transactions", "dim_month", "dim_town", "dim_flat_type", "dim_storey_range", "dim_flat_model"]


# Plain-language labels shown in the report (docs/DASHBOARD_GLOSSARY.md). Wording only.
MODEL_LABELS = {("static", "B0"): "Overall typical price (benchmark)",
                ("static", "B1"): "Long-run town and flat-type price (benchmark)",
                ("static", "B2"): "Simple benchmark (recent typical price)",
                ("static", "L-A"): "Simple formula model",
                ("static", "L-B"): "Simple formula model + street",
                ("static", "G-A"): "Advanced model, no street detail",
                ("static", "G-B"): "Chosen model (not updated)",
                ("monthly refit", "G-B"): "Chosen model (updated monthly)",
                ("monthly refit", "B2"): "Simple benchmark (updated monthly)"}
SEGMENT_LABELS = {"flat_type": "Flat type", "town": "Town", "flat_model": "Flat model",
                  "storey_range": "Floor level", "price_quintile": "Price level", "month": "Month"}
QUINTILE_LABELS = {"Q1 (lowest)": "Cheapest 20%", "Q2": "Lower-middle 20%", "Q3": "Middle 20%",
                   "Q4": "Upper-middle 20%", "Q5 (highest)": "Most expensive 20%"}
RELIABILITY_LABELS = {"ok": "Yes", "less reliable (n<30)": "Few sales"}
EVIDENCE_LABELS = {"Supported": "Strong evidence", "Material composition effect": "Strong evidence",
                   "No material composition effect": "No clear effect", "Inconclusive": "Unclear"}


def floors_label(storey_range: str) -> str:
    """'01 TO 03' -> 'Floors 1-3'."""
    lo, hi = storey_range.split(" TO ")
    return f"Floors {int(lo)}-{int(hi)}"


def month_label(yyyy_mm: str) -> str:
    """'2026-09' -> 'Sep 2026'."""
    return pd.Timestamp(yyyy_mm[:7] + "-01").strftime("%b %Y")


def hypothesis_plain(row: pd.Series) -> tuple[str, str, str, str]:
    """(question, what the data shows, size of effect, likely range) in plain words, from the numbers."""
    h, est, lo, hi = row["hypothesis"], row["estimate_pct"], row["ci_low_pct"], row["ci_high_pct"]
    rng = f"{lo:.1f}% to {hi:.1f}%" if pd.notna(lo) else "-"
    if h == "H1":
        return "Do higher floors sell for more?", f"10 floors higher: about {est:.1f}% more", f"+{est:.1f}%", rng
    if h == "H2":
        return "Does more lease left add value?", f"10 more years of lease: about {est:.1f}% more", f"+{est:.1f}%", rng
    if h == "H3":
        return "Do bigger flats of the same type sell for more?", f"10 sqm more space: about {est:.1f}% more", f"+{est:.1f}%", rng
    if h == "H4":
        share = 100 * row["effect_size"]
        return ("Does the town matter for 4-room flats?",
                f"Town accounts for about {share:.0f}% of 4-room price differences", f"{share:.0f}% of differences", "-")
    return ("Does the headline price trend tell the full story?",
            f"Headline understates like-for-like growth by {abs(est):.1f} points", f"{est:.1f} points", "-")


FEATURE_LABELS = {"floor_area_sqm_num": "Floor area", "town": "Town", "lease_commence_year": "Lease start year",
                  "flat_type": "Flat type", "street_name": "Street", "storey_mid": "Storey",
                  "flat_model": "Flat model", "remaining_lease_years": "Remaining lease",
                  "months_since_start": "Month (time)"}


class CrossCheckError(RuntimeError):
    pass


def _lease_reference_band(effects: pd.DataFrame) -> str:
    """The M2 reference lease band is the 5-year band just below the lowest band with a coefficient."""
    lowest = min(int(level[:2]) for level in effects["level"])
    lo = lowest - 5
    return f"{lo:02d}-{lo + 4:02d}"


def build_sqlite(clean: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    cols = ["source_row_number", "month", "town", "flat_type", "flat_model", "storey_range", "storey_lower",
            "storey_mid", "floor_area_sqm_num", "remaining_lease_years", "lease_commence_year",
            "resale_price_sgd", "price_per_sqm_sgd", "is_partial_month"]
    clean[cols].assign(is_partial_month=clean["is_partial_month"].astype(int),
                       storey_lower=clean["storey_lower"].astype(int),
                       lease_commence_year=clean["lease_commence_year"].astype("float64")
                       ).to_sql("clean", con, index=False)
    for script in sorted(SQL_DIR.glob("*.sql")):
        con.executescript(script.read_text(encoding="utf-8"))
    return con


def cross_check(con: sqlite3.Connection, clean: pd.DataFrame) -> dict:
    """SQL vs pandas: monthly counts/medians and latest-12m town x type medians must match."""
    sql_m = pd.read_sql("SELECT * FROM agg_monthly", con).set_index("month")
    pd_m = clean.groupby(clean["month"] + "-01")["resale_price_sgd"].agg(["size", "median"])
    if not (sql_m["transactions"].equals(pd_m["size"].astype("int64"))
            and np.allclose(sql_m["median_price"], pd_m["median"], rtol=0, atol=1e-6)):
        raise CrossCheckError("Monthly SQL aggregates differ from pandas")
    full = clean[~clean["is_partial_month"]]
    last = full["month_date"].max()
    l12 = full[full["month_date"] > last - pd.DateOffset(months=12)]
    pd_t = l12.groupby(["town", "flat_type"])["resale_price_sgd"].agg(["size", "median"])
    sql_t = pd.read_sql("SELECT * FROM agg_town_flat_type_latest12", con).set_index(["town", "flat_type"])
    if not (sql_t["transactions"].equals(pd_t["size"].astype("int64").reindex(sql_t.index))
            and np.allclose(sql_t["median_price"], pd_t["median"].reindex(sql_t.index), rtol=0, atol=1e-6)):
        raise CrossCheckError("Town x flat type SQL aggregates differ from pandas")
    return {"monthly_rows_checked": int(len(sql_m)), "town_flat_type_cells_checked": int(len(sql_t)),
            "result": "match"}


def dax_expected(fact: pd.DataFrame, dim_month: pd.DataFrame) -> pd.DataFrame:
    """Expected results for DAX measures under explicit filter contexts (validated in Power BI)."""
    f = fact.merge(dim_month[["month", "is_partial_month", "is_latest_12m", "is_prior_12m"]], on="month")
    full = f[f["is_partial_month"] == 0]
    l12, p12 = f[f["is_latest_12m"] == 1], f[f["is_prior_12m"] == 1]
    bedok4 = l12[(l12["town"] == "BEDOK") & (l12["flat_type"] == "4 ROOM")]
    rows = [
        ("Transactions", "no filter", len(f)),
        ("Transactions (Full Months)", "no filter", len(full)),
        ("Median Price (Full Months)", "no filter", full["resale_price"].median()),
        ("Median Price Latest 12M", "no filter", l12["resale_price"].median()),
        ("Median Price Prior 12M", "no filter", p12["resale_price"].median()),
        ("Median Price YoY %", "no filter", l12["resale_price"].median() / p12["resale_price"].median() - 1),
        ("Transactions Latest 12M", "no filter", len(l12)),
        ("Median Price Latest 12M", "town=BEDOK, flat_type=4 ROOM", bedok4["resale_price"].median()),
        ("P25 Price Latest 12M", "town=BEDOK, flat_type=4 ROOM", bedok4["resale_price"].quantile(0.25)),
        ("P75 Price Latest 12M", "town=BEDOK, flat_type=4 ROOM", bedok4["resale_price"].quantile(0.75)),
        ("Median Price per sqm Latest 12M", "town=BEDOK, flat_type=4 ROOM", bedok4["price_per_sqm"].median()),
        ("Transactions Latest 12M", "town=BEDOK, flat_type=4 ROOM", len(bedok4)),
        ("Mean Price Latest 12M", "no filter", l12["resale_price"].mean()),
    ]
    return pd.DataFrame(rows, columns=["measure", "filter_context", "expected_value"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    cur = cfg.curated_dir
    cur.mkdir(parents=True, exist_ok=True)
    clean = load_clean(cfg)
    clean["month"] = clean["month_date"].dt.strftime("%Y-%m")

    con = build_sqlite(clean)
    check = cross_check(con, clean)
    log.info("SQL vs pandas cross-check: %s", check)
    tables = {t: pd.read_sql(f"SELECT * FROM {t}", con) for t in STAR_TABLES}
    for t, df in tables.items():
        df.to_csv(cur / f"{t}.csv", index=False, float_format="%.6g" if t != "fact_transactions" else None)
    pd.read_sql("SELECT * FROM agg_town_flat_type_latest12", con).to_csv(
        cur / "sql_check_town_flat_type_latest12.csv", index=False)
    con.close()

    # Analysis and model outputs used by the report (copied with stable names)
    tab, mm = cfg.outputs_dir / "tables", cfg.outputs_dir / "model_metrics"
    copies = {
        "price_index_monthly.csv": tab / "price_index_monthly.csv",
        "hypothesis_results.csv": tab / "hypothesis_results.csv",
        "town_effects_adjusted.csv": tab / "town_effects_adjusted_recent.csv",
        "storey_effects_adjusted.csv": tab / "storey_band_effects_adjusted_recent.csv",
        "lease_effects_adjusted.csv": tab / "lease_band_effects_adjusted_recent.csv",
        "model_errors_by_month.csv": mm / "test_errors_by_month.csv",
        "model_segment_errors.csv": mm / "test_segment_errors_static.csv",
        "model_feature_importance.csv": mm / "permutation_importance.csv",
    }
    # Reference level of each adjusted-effect curve (0% by definition), so charts start at the baseline.
    for name, src in copies.items():
        df = pd.read_csv(src)
        if name in ("price_index_monthly.csv", "model_errors_by_month.csv"):
            df["month"] = df["month"] + "-01"
        if name == "storey_effects_adjusted.csv":
            df = pd.concat([pd.DataFrame([{"level": "01 TO 03", "pct_vs_reference": 0.0, "ci_low": 0.0,
                                           "ci_high": 0.0}]), df], ignore_index=True)
            df["level_label"] = df["level"].map(floors_label)
            df["level_order"] = df["level"].str[:2].astype(int)
        if name == "lease_effects_adjusted.csv":
            ref_band = _lease_reference_band(df)
            df = pd.concat([pd.DataFrame([{"level": ref_band, "pct_vs_reference": 0.0, "ci_low": 0.0,
                                           "ci_high": 0.0}]), df], ignore_index=True)
            df["level_order"] = df["level"].str[:2].astype(int)  # numeric axis: years of lease left
        if name == "model_segment_errors.csv":
            df["segment_label"] = df["segment"].map(SEGMENT_LABELS)
            df["level_label"] = df["level"].map(QUINTILE_LABELS).fillna(df["level"])
            is_storey, is_month = df["segment"] == "storey_range", df["segment"] == "month"
            df.loc[is_storey, "level_label"] = df.loc[is_storey, "level"].map(floors_label)
            df.loc[is_month, "level_label"] = df.loc[is_month, "level"].map(month_label)
            # Flat-model names can look like flat types ("2-room" vs "2 ROOM"); prefix them (review 4).
            is_model = df["segment"] == "flat_model"
            df.loc[is_model, "level_label"] = "Model: " + df.loc[is_model, "level"]
            df["reliability_label"] = df["reliability"].map(RELIABILITY_LABELS)
        if name == "model_feature_importance.csv":
            df["feature_label"] = df["feature"].map(FEATURE_LABELS).fillna(df["feature"])
        df.to_csv(cur / name, index=False, float_format="%.6g")

    # Model comparison with plain-English labels (static rows + monthly-refit rows)
    labels = MODEL_LABELS
    ts = pd.read_csv(mm / "test_scores.csv")
    ts["model_label"] = [labels[(m, f)] for m, f in zip(ts["mode"], ts["family"])]
    # The report compares the realistic baseline with the candidate models; B0/B1 (naive baselines)
    # and the B2 monthly-refit row stay in the model card and outputs/model_metrics/test_scores.csv.
    ts = ts[~ts["model_label"].isin([labels[("static", "B0")], labels[("static", "B1")],
                                     labels[("monthly refit", "B2")]])]
    ts[["model_label", "mode", "family", "config", "n", "mae", "rmse", "r2", "medae", "mdape_pct",
        "bias_median_pct"]].to_csv(cur / "model_comparison.csv", index=False, float_format="%.6g")

    h5 = json.loads((tab / "analysis_results.json").read_text(encoding="utf-8"))["h5"]
    hyp = pd.read_csv(cur / "hypothesis_results.csv")
    hyp["plain_english"] = hyp["hypothesis"].map({
        "H1": "Higher floor, otherwise comparable flat", "H2": "More remaining lease, otherwise comparable",
        "H3": "Larger floor area within the same flat type", "H4": "Town differences for 4-ROOM flats"})
    hyp = pd.concat([hyp, pd.DataFrame([{
        "hypothesis": "H5", "contrast": f"Raw vs mix-adjusted change, {h5['base_period']} to {h5['comparison_period']}",
        "method": "Hedonic time-dummy index vs raw median", "population": "full period", "n": h5["n_comparison"],
        "estimate_pct": h5["difference_pp"], "ci_low_pct": np.nan, "ci_high_pct": np.nan,
        "status": h5["status"], "plain_english": "How much of the headline change is mix (percentage points)"}])])
    plain = hyp.apply(hypothesis_plain, axis=1, result_type="expand")
    hyp["question"], hyp["finding"], hyp["size_of_effect"], hyp["likely_range"] = (plain[i] for i in range(4))
    hyp["evidence"] = hyp["status"].map(EVIDENCE_LABELS).fillna(hyp["status"])
    hyp["hypothesis_order"] = hyp["hypothesis"].str[1:].astype(int)  # show findings in question order
    hyp.to_csv(cur / "hypothesis_results.csv", index=False, float_format="%.6g")

    # Indicative profiles (refit selected model on all full months)
    df = add_time_index(analysis_ready(clean))
    seg_roll = pd.read_csv(mm / "test_segment_errors_monthly_refit.csv")
    prof = estimate_profiles(df, seg_roll)
    prof.to_csv(cur / "indicative_profiles.csv", index=False, float_format="%.6g")
    log.info("Profiles: %d rows; estimate vs segment median: median %.1f%%, range %.1f%% to %.1f%%", len(prof),
             prof["estimate_vs_segment_median_pct"].median(), prof["estimate_vs_segment_median_pct"].min(),
             prof["estimate_vs_segment_median_pct"].max())

    run = json.loads((cfg.processed_dir / "run_info.json").read_text(encoding="utf-8"))
    dm = tables["dim_month"]
    pd.DataFrame([{
        "snapshot_id": run["snapshot_id"], "dataset_id": run["dataset_id"],
        "retrieved_at_local": run["retrieved_at_local"][:16].replace("T", " "),
        "source_last_updated_at": run["source_last_updated_at"][:16].replace("T", " "),
        "first_month": run["first_month"], "last_full_month": dm.loc[dm["is_partial_month"] == 0, "month"].max()[:7],
        "partial_month": ", ".join(run["partial_months"]) or "none",
        "first_month_label": month_label(run["first_month"]),
        "last_full_month_label": month_label(dm.loc[dm["is_partial_month"] == 0, "month"].max()),
        "partial_month_label": ", ".join(month_label(m) for m in run["partial_months"]) or "None",
        "retrieved_label": pd.Timestamp(run["retrieved_at_local"][:16]).strftime("%d %b %Y, %H:%M") + " SGT",
        "clean_rows": run["clean_rows"], "quarantined_rows": run["quarantined_rows"],
        "attribution": "Contains information from Resale flat prices based on registration date from Jan-2017 "
                       "onwards (HDB) accessed from data.gov.sg, made available under the Singapore Open Data "
                       "Licence v1.0. Not endorsed by HDB.",
    }]).to_csv(cur / "refresh_info.csv", index=False)

    exp = dax_expected(tables["fact_transactions"], dm)
    exp.to_csv(cur / "dax_expected_values.csv", index=False, float_format="%.10g")
    (cur / "build_info.json").write_text(json.dumps({"snapshot_id": run["snapshot_id"], "sql_cross_check": check,
                                                     "fact_rows": int(len(tables["fact_transactions"])),
                                                     "profiles": int(len(prof))}, indent=2), encoding="utf-8")
    log.info("Curated tables written to %s", cur)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
