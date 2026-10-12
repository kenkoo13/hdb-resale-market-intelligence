"""Phase 3 entry point: train, select (validation only), evaluate on test, analyse errors.

Usage
    python -m src.modelling.run_modelling            # full run (~10-20 min)
    python -m src.modelling.run_modelling --sample 0.1   # quick smoke run on a 10% sample

Procedure (docs/MODEL_CARD.md §3-6)
    1. Chronological split from the last full month.
    2. Fit B0, B1 and all 20 candidate configurations on TRAIN; score on VALIDATION.
    3. Select by validation MAE (1% tie-break towards simpler). Also keep the best
       configuration of each family for the comparison table.
    4. Static test: refit each family's best configuration on TRAIN+VALIDATION,
       predict all 12 TEST months once.
    5. Monthly refit: for each test month m, refit the selected configuration
       (and baseline B2) on all data before m, predict month m.
    6. 80% split-conformal intervals calibrated on validation residuals of the
       train-only selected model; coverage reported on test.
    7. Segment errors and permutation importance for the selected model.

Outputs
    outputs/model_metrics/*.csv, model_results.json   (committed)
    outputs/figures/1x_*.png                          (committed)
    data/processed/model_test_predictions.parquet     (git-ignored; feeds Phase 4)
    outputs/models/selected_model.joblib              (git-ignored)
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from src.analytics.common import analysis_ready, load_clean, run_snapshot_id
from src.config import load_config
from src.modelling import evaluate as E
from src.modelling import models as M
from src.modelling.features import FEATURE_SETS, TARGET, add_time_index, build_features
from src.modelling.splits import make_split

log = logging.getLogger("modelling")
TIE_TOLERANCE = 0.01
PRICE_QUINTILE_LABELS = ["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"]


def _cfg_name(c: dict[str, Any]) -> str:
    return f"{c['family']} " + ", ".join(f"{k}={v}" for k, v in c["params"].items())


def _fit_predict(model, train: pd.DataFrame, target: pd.DataFrame, fs: str) -> tuple[Any, np.ndarray]:
    model.fit(build_features(train, fs), train[TARGET])
    return model, model.predict(build_features(target, fs))


def _baselines() -> list[tuple[str, object]]:
    """B0, B1 pre-specified; B2 (last-12-month segment median) added after the smoke run (DEC-021)."""
    return [("B0", M.GlobalMedianBaseline()), ("B1", M.SegmentMedianBaseline()),
            ("B2", M.SegmentMedianBaseline(recent_months=12))]


def select(val_table: pd.DataFrame, configs: list[dict]) -> dict:
    """Lowest validation MAE; within 1% prefer the simplest (MODEL_CARD §6)."""
    cand = val_table[val_table["family"].str.match(r"^[LG]-")].copy()
    best_mae = cand["mae"].min()
    near = cand[cand["mae"] <= best_mae * (1 + TIE_TOLERANCE)].copy()
    near["rank"] = near["config_id"].map(lambda i: M.complexity_rank(configs[i]))
    chosen = near.sort_values(["rank", "mae"]).iloc[0]
    return configs[int(chosen["config_id"])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=float, default=None, help="fraction of rows for a smoke run")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    out_dir, fig_dir = cfg.outputs_dir / "model_metrics", cfg.outputs_dir / "figures"
    if args.sample:
        out_dir = out_dir / "smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    df = add_time_index(analysis_ready(load_clean(cfg)))
    if args.sample:
        df = df.sample(frac=args.sample, random_state=cfg.random_seed)
    split = make_split(df)
    parts = split.assign(df)
    train, val, test = parts["train"], parts["validation"], parts["test"]
    split_info = split.describe(df)
    log.info("Split: %s", split_info)

    # Unseen categories relative to the training data
    unseen = {}
    for col in ["town", "flat_type", "flat_model", "street_name"]:
        seen = set(train[col])
        unseen[col] = {"validation_rows": int((~val[col].isin(seen)).sum()),
                       "test_rows_vs_train_val": int((~test[col].isin(seen | set(val[col]))).sum()),
                       "validation_levels": sorted(set(val[col]) - seen)[:20]}

    # ---------- 1. Validation: baselines + grid ----------
    configs = M.candidate_grid()
    rows, train_rows = [], []
    for name, model in _baselines():
        model, pred = _fit_predict(model, train, val, "A")
        rows.append({"config_id": -1, "family": name, "config": name, **E.metrics(val[TARGET], pred)})
    for i, c in enumerate(configs):
        t = time.time()
        model, pred = _fit_predict(M.build(c), train, val, c["feature_set"])
        r = {"config_id": i, "family": c["family"], "config": _cfg_name(c), **E.metrics(val[TARGET], pred),
             "fit_seconds": round(time.time() - t, 1)}
        if c["model"] == "hgb":
            r["n_iter"] = int(model.regressor_.named_steps["model"].n_iter_)
        rows.append(r)
        tr_pred = model.predict(build_features(train, c["feature_set"]))
        train_rows.append({"config_id": i, "config": _cfg_name(c), **E.metrics(train[TARGET], tr_pred)})
        log.info("VAL %-55s MAE %9.0f (%.0fs)", _cfg_name(c), r["mae"], r["fit_seconds"])
    val_table = pd.DataFrame(rows)
    train_table = pd.DataFrame(train_rows)
    selected = select(val_table, configs)
    best_per_family = {fam: configs[int(g.sort_values("mae").iloc[0]["config_id"])]
                       for fam, g in val_table[val_table["config_id"] >= 0].groupby("family")}
    log.info("Selected: %s", _cfg_name(selected))

    # ---------- 2. Calibration residuals (train-only selected model on validation) ----------
    _, val_pred_sel = _fit_predict(M.build(selected), train, val, selected["feature_set"])
    q_lo, q_hi = E.conformal_quantiles(val[TARGET], val_pred_sel, 0.8)

    # ---------- 3. Static test ----------
    trval = pd.concat([train, val])
    test_rows, preds = [], test[["month", "town", "flat_type", "flat_model", "storey_range", "floor_area_sqm_num",
                                 "remaining_lease_years", "street_name", TARGET]].copy()
    for name, model in _baselines():
        _, p = _fit_predict(model, trval, test, "A")
        preds[f"pred_static_{name}"] = p
        test_rows.append({"mode": "static", "family": name, "config": name, **E.metrics(test[TARGET], p)})
    final_models = {}
    for fam, c in sorted(best_per_family.items()):
        model, p = _fit_predict(M.build(c), trval, test, c["feature_set"])
        final_models[fam] = model
        preds[f"pred_static_{fam}"] = p
        test_rows.append({"mode": "static", "family": fam, "config": _cfg_name(c),
                          "selected": c is selected, **E.metrics(test[TARGET], p)})
    sel_fam = selected["family"]
    preds["predicted"] = preds[f"pred_static_{sel_fam}"]
    preds["actual"] = preds[TARGET]
    preds["interval_low"], preds["interval_high"] = E.apply_interval(preds["predicted"], q_lo, q_hi)

    # ---------- 4. Monthly refit (rolling origin) ----------
    full = pd.concat([train, val, test])
    roll_sel, roll_b2 = pd.Series(index=test.index, dtype=float), pd.Series(index=test.index, dtype=float)
    for m in sorted(test["month"].unique()):
        hist = full[full["month"] < m]
        tgt = test[test["month"] == m]
        _, p = _fit_predict(M.build(selected), hist, tgt, selected["feature_set"])
        roll_sel.loc[tgt.index] = p
        _, pb = _fit_predict(M.SegmentMedianBaseline(recent_months=12), hist, tgt, "A")
        roll_b2.loc[tgt.index] = pb
        log.info("Rolling %s: MAE %.0f (B2 %.0f)", m, E.metrics(tgt[TARGET], p)["mae"],
                 E.metrics(tgt[TARGET], pb)["mae"])
    preds["predicted_rolling"] = roll_sel
    preds["pred_rolling_B2"] = roll_b2
    test_rows.append({"mode": "monthly refit", "family": sel_fam, "config": _cfg_name(selected), "selected": True,
                      **E.metrics(test[TARGET], roll_sel)})
    test_rows.append({"mode": "monthly refit", "family": "B2", "config": "B2", **E.metrics(test[TARGET], roll_b2)})
    roll_lo, roll_hi = (pd.Series(a, index=roll_sel.index) for a in E.apply_interval(roll_sel, q_lo, q_hi))
    test_table = pd.DataFrame(test_rows)

    # ---------- 5. Errors by segment and horizon ----------
    preds["price_quintile"] = pd.qcut(preds["actual"], 5, labels=PRICE_QUINTILE_LABELS)
    preds["horizon_months"] = preds["month"].map({m: i + 1 for i, m in enumerate(sorted(test["month"].unique()))})
    seg = pd.concat([E.segment_errors(preds, s) for s in
                     ["flat_type", "town", "flat_model", "storey_range", "price_quintile", "month"]])
    roll_view = preds.assign(predicted=preds["predicted_rolling"])
    seg_roll = pd.concat([E.segment_errors(roll_view, s) for s in ["flat_type", "town", "price_quintile", "month"]])
    by_month = pd.DataFrame([
        {"month": m, "horizon_months": int(g["horizon_months"].iloc[0]), "n": len(g),
         "mae_static": E.metrics(g["actual"], g["predicted"])["mae"],
         "mae_monthly_refit": E.metrics(g["actual"], g["predicted_rolling"])["mae"],
         "mae_B2_monthly_refit": E.metrics(g["actual"], g["pred_rolling_B2"])["mae"],
         "bias_static_pct": E.metrics(g["actual"], g["predicted"])["bias_median_pct"],
         "bias_monthly_refit_pct": E.metrics(g["actual"], g["predicted_rolling"])["bias_median_pct"],
         "coverage80_static": E.coverage(g["actual"], g["interval_low"], g["interval_high"]),
         "coverage80_monthly_refit": E.coverage(g["actual"], roll_lo[g.index], roll_hi[g.index])}
        for m, g in preds.groupby("month")])

    # ---------- 6. Permutation importance (selected static model, test sample) ----------
    fs = selected["feature_set"]
    samp = test.sample(n=min(5000, len(test)), random_state=cfg.random_seed)
    pi = permutation_importance(final_models[sel_fam], build_features(samp, fs), samp[TARGET],
                                scoring="neg_mean_absolute_error", n_repeats=5, random_state=cfg.random_seed)
    importance = pd.DataFrame({"feature": FEATURE_SETS[fs], "mae_increase_sgd": pi.importances_mean,
                               "std": pi.importances_std}).sort_values("mae_increase_sgd", ascending=False)

    # ---------- Save ----------
    for name, t in {"validation_scores": val_table, "train_scores": train_table, "test_scores": test_table,
                    "test_segment_errors_static": seg, "test_segment_errors_monthly_refit": seg_roll,
                    "test_errors_by_month": by_month, "permutation_importance": importance}.items():
        t.to_csv(out_dir / f"{name}.csv", index=False, float_format="%.6g")
    results = {
        "snapshot_id": run_snapshot_id(cfg), "sample_fraction": args.sample, "split": split_info,
        "unseen_categories": unseen, "selected_config": _cfg_name(selected),
        "best_per_family": {k: _cfg_name(v) for k, v in best_per_family.items()},
        "conformal_80": {"q_low_log": q_lo, "q_high_log": q_hi,
                         "multiplier_low": float(np.exp(q_lo)), "multiplier_high": float(np.exp(q_hi)),
                         "coverage_test_static": E.coverage(preds["actual"], preds["interval_low"],
                                                            preds["interval_high"]),
                         "coverage_test_monthly_refit": E.coverage(preds["actual"], roll_lo, roll_hi)},
        "runtime_seconds": round(time.time() - t0),
    }
    (out_dir / "model_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    if not args.sample:
        preds.assign(predicted_monthly_refit=preds["predicted_rolling"]).to_parquet(
            cfg.processed_dir / "model_test_predictions.parquet", index=False)
        (cfg.outputs_dir / "models").mkdir(parents=True, exist_ok=True)
        joblib.dump(final_models[sel_fam], cfg.outputs_dir / "models" / "selected_model.joblib")
        # Figures are always drawn from the saved outputs (one code path), so a rerun and
        # `python -m src.reporting.model_figures` give pixel-identical PNGs (Phase 5 finding).
        from src.reporting import model_figures as MF
        MF.regenerate()

    log.info("Done in %.0fs", time.time() - t0)
    print(test_table.to_string())
    print(json.dumps(results["conformal_80"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
