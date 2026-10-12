"""Phase 2 entry point: descriptive analysis, hedonic models, hypotheses H1-H5, figures.

Usage
    python -m src.analytics.run_analysis

Inputs
    data/processed/transactions_clean.parquet and run_info.json (from src.pipeline).

Outputs (all regenerated on every run; small, committed)
    outputs/tables/*.csv              descriptive and inferential tables
    outputs/tables/analysis_results.json  hypothesis results, diagnostics, windows
    outputs/figures/*.png             figures used in README / docs

Reproducibility
    Deterministic apart from the H5 bootstrap, which uses the configured seed (42).
"""
from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd

from src.analytics import descriptive as D
from src.analytics import hedonic as H
from src.analytics import hypotheses as HY
from src.analytics.common import analysis_ready, get_windows, in_window, load_clean, run_snapshot_id
from src.config import load_config
from src.reporting import figures as F
from src.transformation.clean import FLAT_TYPE_ORDER

log = logging.getLogger("analysis")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    tables, figs = cfg.outputs_dir / "tables", cfg.outputs_dir / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    clean = load_clean(cfg)
    df = analysis_ready(clean)
    df = D.add_bands(H.add_lease_band(df))
    w = get_windows(df)
    recent = in_window(df, w.recent_start, w.last_full_month)
    latest12 = in_window(df, w.latest12_start, w.last_full_month)
    recent_label = w.label(w.recent_start)
    log.info("Analysis-ready rows %d; recent window %s (%d rows)", len(df), recent_label, len(recent))

    # ---------- Descriptive tables ----------
    monthly = D.monthly_market(clean)
    out = {
        "monthly_market": monthly,
        "annual_by_flat_type": D.segment_summary(df, ["year", "flat_type"]),
        "mix_over_time": D.mix_over_time(df),
        "price_distribution_summary": pd.DataFrame([
            D.distribution_summary(df, f"full period {w.label(w.first_full_month)}"),
            D.distribution_summary(recent, f"recent window {recent_label}")]),
        "recent_by_flat_type": D.segment_summary(recent, "flat_type"),
        "recent_by_town": D.segment_summary(recent, "town"),
        "recent_4room_by_town": D.segment_summary(recent[recent["flat_type"] == "4 ROOM"], "town"),
        "recent_by_town_flat_type": D.thin_cells(recent),
        "recent_by_storey_range": D.segment_summary(recent, "storey_range"),
        "recent_by_floor_area_band_flat_type": D.segment_summary(recent, ["flat_type", "floor_area_band"]),
        "recent_by_flat_model": D.segment_summary(recent, "flat_model"),
        "recent_by_lease_band": D.segment_summary(recent, "lease_band"),
    }

    # ---------- Hedonic fits ----------
    fits = {}
    for name, data, formula in [("m1_recent", recent, H.M1_FORMULA), ("m2_recent", recent, H.M2_FORMULA),
                                ("m1_full", df, H.M1_FORMULA),
                                ("m1_nodup", recent[recent["duplicate_group_size"] == 1], H.M1_FORMULA)]:
        t = time.time()
        fits[name] = H.fit(data, formula)
        log.info("Fitted %s: n=%d, R2=%.4f (%.1fs)", name, fits[name].nobs, fits[name].rsquared, time.time() - t)

    diag = {k: H.diagnostics(fits[k], d).__dict__ for k, d in [("m1_recent", recent), ("m1_full", df)]}

    # ---------- Hypotheses ----------
    rows, robust, details = HY.run_h1_h4(recent, df, fits)
    months = sorted(df["month"].unique())
    base_months = [m for m in months if m.startswith(str(w.first_full_month.year))]
    comp_months = sorted(latest12["month"].unique())
    h5 = HY.run_h5(df, fits["m1_full"], months, base_months, comp_months, cfg.random_seed)
    results = pd.DataFrame(rows)
    out["hypothesis_results"] = results
    out["hypothesis_robustness"] = pd.DataFrame(robust)
    out["h5_composition"] = pd.DataFrame([h5])
    out["town_effects_adjusted_recent"] = details["town_effects_m1"]
    out["storey_band_effects_adjusted_recent"] = details["m2_storey_bands"]
    out["lease_band_effects_adjusted_recent"] = details["m2_lease_bands"]
    fm = H.categorical_effects(fits["m1_recent"], "flat_model")
    fm["n_recent"] = fm["level"].map(recent["flat_model"].value_counts())
    # Aliased with flat_type MULTI-GENERATION (same flats): only the sum is identified.
    fm["separately_identified"] = fm["level"] != "Multi Generation"
    out["flat_model_effects_adjusted_recent"] = fm.sort_values("pct_vs_reference")
    key_terms = ["floor_area_sqm_num", "storey_mid", "remaining_lease_years"]
    out["hedonic_key_coefficients"] = pd.DataFrame([
        {"model": k, "term": t, **H.pct_effect(fits[k], t, 1)} for k in ["m1_recent", "m1_full", "m1_nodup"]
        for t in key_terms])

    # Mix-adjusted vs raw monthly index (base: first full calendar year = 100)
    idx = H.month_index(fits["m1_full"], months)
    base_adj = idx.loc[idx["month"].isin(base_months), "index"].mean()
    raw_med = df.groupby("month")["resale_price_sgd"].median()
    base_raw = df.loc[df["month"].isin(base_months), "resale_price_sgd"].median()
    idx["mix_adjusted_index"] = 100 * idx["index"] / base_adj
    idx["raw_median_index"] = 100 * idx["month"].map(raw_med) / base_raw
    idx["transactions"] = idx["month"].map(df.groupby("month").size())
    out["price_index_monthly"] = idx[["month", "transactions", "raw_median_index", "mix_adjusted_index"]]

    for name, table in out.items():
        table.to_csv(tables / f"{name}.csv", index=False, float_format="%.6g")

    summary = {
        "snapshot_id": run_snapshot_id(cfg),
        "windows": {"full_period": w.label(w.first_full_month), "recent_window": recent_label,
                    "latest_12_months": w.label(w.latest12_start)},
        "rows": {"analysis_ready": int(len(df)), "recent_window": int(len(recent)),
                 "latest_12_months": int(len(latest12))},
        "hypotheses": results.replace({np.nan: None}).to_dict(orient="records"),
        "robustness": robust, "h4_details": details["h4"], "h5": h5, "diagnostics": diag,
    }
    (tables / "analysis_results.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # ---------- Figures ----------
    F.monthly_volume(monthly, figs / "01_monthly_volume.png")
    F.monthly_median(monthly, figs / "02_monthly_median_price.png")
    F.raw_vs_adjusted_index(out["price_index_monthly"], figs / "03_raw_vs_mix_adjusted_index.png",
                            str(w.first_full_month.year))
    F.price_distribution(recent, figs / "04_price_distribution_recent.png", f"recent window {recent_label}")
    ft = out["recent_by_flat_type"]
    F.segment_bars(ft, "flat_type", figs / "05_median_price_by_flat_type.png",
                   "What does each flat type typically sell for?",
                   f"Median resale price by flat type, {recent_label}; whiskers show 25th-75th percentile",
                   order=[x for x in FLAT_TYPE_ORDER if x in set(ft["flat_type"])])
    F.segment_bars(out["recent_4room_by_town"], "town", figs / "06_4room_median_by_town.png",
                   "Where do 4-ROOM flats cost more?",
                   f"Median 4-ROOM resale price by town, {recent_label}; whiskers = 25th-75th percentile",
                   horizontal=True)
    raw_storey = out["recent_by_storey_range"].assign(mid=lambda x: x["storey_range"].str[:2].astype(int) + 1)
    adj_storey = pd.concat([pd.DataFrame([{"mid": 2, "pct_vs_reference": 0.0, "ci_low": 0.0, "ci_high": 0.0}]),
                            details["m2_storey_bands"]]).sort_values("mid")
    F.effect_panels(raw_storey.sort_values("mid"), adj_storey, "mid", figs / "07_storey_raw_vs_adjusted.png",
                    "Higher floors: raw medians vs like-for-like comparison",
                    f"Recent window {recent_label}. Adjusted = hedonic model M2 holding month, town, type, "
                    "model, area and lease fixed", "Storey (band midpoint)")
    raw_lease = out["recent_by_lease_band"].assign(mid=lambda x: x["lease_band"].str[:2].astype(int) + 2.5)
    ref_lease = H.reference_level(recent, "lease_band")
    adj_lease = pd.concat([pd.DataFrame([{"mid": int(ref_lease[:2]) + 2.5, "pct_vs_reference": 0.0,
                                          "ci_low": 0.0, "ci_high": 0.0}]),
                           details["m2_lease_bands"]]).sort_values("mid")
    F.effect_panels(raw_lease.sort_values("mid"), adj_lease, "mid", figs / "08_lease_raw_vs_adjusted.png",
                    "Remaining lease: raw medians vs like-for-like comparison",
                    f"Recent window {recent_label}. Adjusted = hedonic model M2 holding month, town, type, "
                    "model, area and storey fixed", "Remaining lease (years, 5-year band midpoint)")
    F.mix_lines(out["mix_over_time"], figs / "09_flat_type_mix.png")

    log.info("Done in %.0fs", time.time() - t0)
    print(results[["hypothesis", "estimate_pct", "ci_low_pct", "ci_high_pct", "p_holm", "status"]].to_string())
    print(json.dumps(h5, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
