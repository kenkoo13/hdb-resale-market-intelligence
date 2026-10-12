"""Figures for model evaluation (same conventions as src/reporting/figures.py, DEC-018)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from src.reporting.figures import AQUA, BLUE, INK, INK2, MUTED, ORANGE, SGD_FULL, SURFACE, _finish, plt

FAMILY_LABELS = {"B0": "B0 Global median", "B1": "B1 Town x type median (all history)",
                 "B2": "B2 Town x type median (last 12 months)", "L-A": "Ridge (set A)",
                 "L-B": "Ridge (set A + street)", "G-A": "Gradient boosting (set A)",
                 "G-B": "Gradient boosting (set A + street)"}


def model_comparison(test_table: pd.DataFrame, path: Path) -> Path:
    t = test_table[test_table["mode"] == "static"].copy()
    t["label"] = t["family"].map(FAMILY_LABELS)
    t = t.sort_values("mae", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colors = [ORANGE if f.startswith("B") else BLUE for f in t["family"]]
    ax.barh(t["label"], t["mae"], color=colors, height=0.6)
    for i, (v, md) in enumerate(zip(t["mae"], t["mdape_pct"])):
        ax.text(v, i, f"  ${v:,.0f}  (typical error {md:.1f}%)", va="center", color=INK2, fontsize=8)
    ax.xaxis.set_major_formatter(SGD_FULL)
    ax.set_xlim(0, t["mae"].max() * 1.45)
    ax.set_xlabel("Mean absolute error on the test year (SGD) - lower is better")
    ax.grid(axis="y", visible=False)
    n = int(t["n"].iloc[0])
    return _finish(fig, ax, "How far off are price estimates, by model?",
                   f"Trained once before the test year, predicting its 12 months (n = {n:,}); "
                   "orange = baselines", path)


def error_by_horizon(by_month: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = by_month["month"]
    series = [("mae_B2_monthly_refit", "B2 baseline (last-12-month median), monthly refit", ORANGE),
              ("mae_static", "Selected model, trained once", BLUE),
              ("mae_monthly_refit", "Selected model, retrained monthly", AQUA)]
    for col, name, color in series:
        ax.plot(x, by_month[col], color=color, marker="o", markersize=4)
        ax.annotate(name, (len(x) - 1, by_month[col].iloc[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=8)
    ax.yaxis.set_major_formatter(SGD_FULL)
    ax.set_ylim(0, by_month[[c for c, _, _ in series]].max().max() * 1.15)
    ax.set_xlim(-0.5, len(x) + 3.5)
    ax.set_ylabel("Mean absolute error (SGD)")
    ax.tick_params(axis="x", rotation=45)
    return _finish(fig, ax, "Does accuracy fade as the model gets older?",
                   "Test-year MAE by month; 'trained once' predicts 1-12 months ahead", path)


def pct_error_distribution(preds: pd.DataFrame, path: Path) -> Path:
    pe = 100 * (preds["predicted"] - preds["actual"]) / preds["actual"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.hist(pe.clip(-40, 40), bins=np.arange(-40, 41, 1), color=BLUE, edgecolor=SURFACE, linewidth=0.4)
    top = ax.get_ylim()[1]
    for q, name, ha, frac in [(0.1, "10th pct", "right", 0.97), (0.5, "median", "left", 0.88),
                              (0.9, "90th pct", "left", 0.97)]:
        v = float(np.quantile(pe, q))
        ax.axvline(v, color=INK if q == 0.5 else MUTED, linewidth=1.2, linestyle="-" if q == 0.5 else "--")
        ax.text(v, top * frac, f" {name}: {v:+.1f}% " if ha == "left" else f"{name}: {v:+.1f}% ",
                color=INK, fontsize=8, va="top", ha=ha,
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1})
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_xlabel("Estimate minus actual, % of actual price (clipped at +/-40%); + = over-estimate")
    ax.set_ylabel("Test transactions")
    return _finish(fig, ax, "How wrong is a typical estimate?",
                   f"Selected model, static test year, n = {len(pe):,}", path)


def mdape_by_segment(seg: pd.DataFrame, segment: str, path: Path, title: str, order: list[str] | None = None) -> Path:
    s = seg[seg["segment"] == segment].set_index("level")
    s = s.loc[[o for o in order if o in s.index]] if order else s.sort_values("mdape_pct")
    fig, ax = plt.subplots(figsize=(10, max(4.2, 0.3 * len(s) + 1.4)))
    # One barh call so bar positions and text positions share the same index.
    ok = (s["reliability"] == "ok").to_numpy()
    y = np.arange(len(s))
    bars = ax.barh(y, s["mdape_pct"], height=0.6, color=[BLUE if o else SURFACE for o in ok],
                   edgecolor=[BLUE if o else MUTED for o in ok])
    for b, o in zip(bars, ok):
        if not o:
            b.set_hatch("///")
    ax.set_yticks(y, [str(i) for i in s.index])
    if (~ok).any():
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(facecolor=SURFACE, edgecolor=MUTED, hatch="///",
                                 label="Fewer than 30 test sales: less reliable")],
                  frameon=False, loc="upper right", fontsize=8)
    for i, (v, n) in enumerate(zip(s["mdape_pct"], s["n"])):
        ax.text(v, i, f"  {v:.1f}%  (n={n:,})", va="center", color=INK2, fontsize=8)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_xlim(0, s["mdape_pct"].max() * 1.35)
    ax.set_xlabel("Median absolute % error (lower is better)")
    ax.grid(axis="y", visible=False)
    return _finish(fig, ax, title, "Selected model, static test year", path)


def make_all(val_table, test_table, by_month, seg, preds, fig_dir: Path) -> None:
    from src.transformation.clean import FLAT_TYPE_ORDER
    model_comparison(test_table, fig_dir / "10_model_comparison_test_mae.png")
    error_by_horizon(by_month, fig_dir / "11_error_by_month_static_vs_refit.png")
    pct_error_distribution(preds, fig_dir / "12_pct_error_distribution.png")
    mdape_by_segment(seg, "flat_type", fig_dir / "13_error_by_flat_type.png",
                     "Which flat types are hardest to estimate?", order=FLAT_TYPE_ORDER[::-1])
    mdape_by_segment(seg, "town", fig_dir / "14_error_by_town.png", "Which towns are hardest to estimate?")


def regenerate(root: Path | None = None) -> None:
    """Rebuild figures 10-14 from saved outputs (no model retraining)."""
    from src.config import load_config
    cfg = load_config()
    d = cfg.outputs_dir / "model_metrics"
    make_all(pd.read_csv(d / "validation_scores.csv"), pd.read_csv(d / "test_scores.csv"),
             pd.read_csv(d / "test_errors_by_month.csv"), pd.read_csv(d / "test_segment_errors_static.csv"),
             pd.read_parquet(cfg.processed_dir / "model_test_predictions.parquet"), cfg.outputs_dir / "figures")


if __name__ == "__main__":
    regenerate()
