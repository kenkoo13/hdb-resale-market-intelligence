"""Static figures (PNG) for the README and documentation.

Design rules (applied consistently)
    * Colours come from a validated categorical palette (blue, orange, aqua as the
      first three slots); at most three coloured series per chart; series are
      direct-labelled so identity never relies on colour alone.
    * One y-axis per chart (no dual axes). Measures of different scale are drawn
      as separate panels.
    * Recessive grid and axes; text in neutral inks, never the series colour.
    * Titles state the takeaway question; subtitles state population, period and n.
    * Currency in SGD with thousands separators.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
VIOLET, YELLOW = "#4a3aa7", "#eda100"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
SOURCE_NOTE = ("Source: HDB resale flat prices (Jan-2017 onwards), data.gov.sg, "
               "Singapore Open Data Licence v1.0. Analysis: this project.")

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "lines.linewidth": 2, "font.family": "sans-serif",
})

SGD = mtick.FuncFormatter(lambda x, _: f"${x / 1000:,.0f}k")
SGD_FULL = mtick.FuncFormatter(lambda x, _: f"${x:,.0f}")


def _finish(fig, ax, title: str, subtitle: str, path: Path) -> Path:
    ax.set_title(title, pad=24)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK2, fontsize=9, va="bottom")
    fig.text(0.01, 0.005, SOURCE_NOTE, color=MUTED, fontsize=7, va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def monthly_volume(monthly: pd.DataFrame, path: Path) -> Path:
    m = monthly.assign(d=pd.to_datetime(monthly["month"]))
    full, part = m[~m["is_partial_month"]], m[m["is_partial_month"]]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(full["d"], full["transactions"], width=25, color=BLUE, label="Full month")
    if len(part):
        ax.bar(part["d"], part["transactions"], width=25, color=SURFACE, edgecolor=MUTED,
               hatch="///", linewidth=0.8, label="Partial month (still accumulating)")
    low = full.nsmallest(2, "transactions").sort_values("d")
    low_text = "; lowest full months " + ", ".join(f"{r['month']} ({r['transactions']:,})" for _, r in low.iterrows())
    ax.set_ylabel("Transactions per month")
    ax.yaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    return _finish(fig, ax, "How many resale flats change hands each month?",
                   f"Registered resale transactions, {m['month'].min()} to {m['month'].max()}{low_text}", path)


def monthly_median(monthly: pd.DataFrame, path: Path) -> Path:
    m = monthly[~monthly["is_partial_month"]].assign(d=lambda x: pd.to_datetime(x["month"]))
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.fill_between(m["d"], m["p25_price"], m["p75_price"], color=BLUE, alpha=0.15, linewidth=0,
                    label="Middle 50% of prices (25th-75th percentile)")
    ax.plot(m["d"], m["median_price"], color=BLUE, label="Median price")
    for idx in [0, len(m) - 1]:
        r = m.iloc[idx]
        ax.annotate(f"${r['median_price']:,.0f}", (r["d"], r["median_price"]), xytext=(0, 10),
                    textcoords="offset points", ha="center", color=INK, fontsize=9, fontweight="bold")
    ax.yaxis.set_major_formatter(SGD)
    ax.set_ylabel("Resale price (SGD)")
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    return _finish(fig, ax, "How have resale prices moved?",
                   f"Monthly median and interquartile range, all flat types, full months "
                   f"{m['month'].iloc[0]} to {m['month'].iloc[-1]}", path)


def raw_vs_adjusted_index(idx: pd.DataFrame, path: Path, base_label: str) -> Path:
    d = pd.to_datetime(idx["month"])
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(d, idx["raw_median_index"], color=ORANGE, linewidth=1.5, label="Raw median price")
    ax.plot(d, idx["mix_adjusted_index"], color=BLUE, label="Mix-adjusted (comparable flats)")
    # End labels: the higher series is labelled above, the lower below, so they never collide.
    last = {c: idx[c].iloc[-1] for c in ["raw_median_index", "mix_adjusted_index"]}
    hi_col = max(last, key=last.get)
    for col, name in [("raw_median_index", "Raw median"), ("mix_adjusted_index", "Mix-adjusted")]:
        ax.annotate(f"{name}: {last[col]:.0f}", (d.iloc[-1], last[col]),
                    xytext=(6, 8 if col == hi_col else -8), textcoords="offset points",
                    va="center", color=INK, fontsize=9)
    ax.axhline(100, color=MUTED, linewidth=0.8)
    ax.set_ylabel(f"Index ({base_label} = 100)")
    ax.set_xlim(d.iloc[0], d.iloc[-1] + pd.DateOffset(months=14))
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    return _finish(fig, ax, "Is the headline price trend driven by which flats were sold?",
                   "Raw monthly median vs hedonic time-dummy index (holds town, type, model, area, "
                   "storey and lease fixed)", path)


def price_distribution(df: pd.DataFrame, path: Path, label: str) -> Path:
    p = df["resale_price_sgd"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.hist(p, bins=np.arange(100_000, p.max() + 25_000, 25_000), color=BLUE, edgecolor=SURFACE, linewidth=0.5)
    for val, name, color, off in [(p.median(), "Median", INK, -6), (p.mean(), "Mean", ORANGE, 6)]:
        ax.axvline(val, color=color, linewidth=1.5, linestyle="--" if name == "Mean" else "-")
        ax.text(val, ax.get_ylim()[1] * 0.95, f" {name} ${val:,.0f} ", color=INK, fontsize=9,
                ha="right" if off < 0 else "left", va="top")
    ax.xaxis.set_major_formatter(SGD)
    ax.set_xlabel("Resale price (SGD, $25k bins)")
    ax.set_ylabel("Transactions")
    return _finish(fig, ax, "Prices are right-skewed, so the median is the fairer 'typical' price",
                   f"Distribution of resale prices, {label}, n = {len(p):,}", path)


def segment_bars(seg: pd.DataFrame, cat: str, path: Path, title: str, subtitle: str,
                 order: list[str] | None = None, horizontal: bool = False) -> Path:
    s = seg.set_index(cat)
    s = s.loc[order] if order else s.sort_values("median_price")
    n = len(s)
    fig, ax = plt.subplots(figsize=(10, max(4.2, 0.32 * n + 1.2)) if horizontal else (10, 4.6))
    labels = [str(x) for x in s.index]
    err = np.vstack([s["median_price"] - s["p25_price"], s["p75_price"] - s["median_price"]])
    if horizontal:
        ax.barh(labels, s["median_price"], color=BLUE, height=0.6)
        ax.errorbar(s["median_price"], labels, xerr=err, fmt="none", ecolor=MUTED, elinewidth=1, capsize=0)
        for i, (v, c, hi) in enumerate(zip(s["median_price"], s["transactions"], s["p75_price"])):
            ax.text(hi, i, f"  ${v / 1000:,.0f}k  (n={c:,})", va="center", color=INK2, fontsize=8)
        ax.xaxis.set_major_formatter(SGD)
        ax.set_xlabel("Median resale price (SGD); whiskers = 25th-75th percentile")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, s["p75_price"].max() * 1.25)
    else:
        ax.bar(labels, s["median_price"], color=BLUE, width=0.6)
        ax.errorbar(labels, s["median_price"], yerr=err, fmt="none", ecolor=MUTED, elinewidth=1)
        for i, (v, c, hi) in enumerate(zip(s["median_price"], s["transactions"], s["p75_price"])):
            ax.text(i, hi, f"${v / 1000:,.0f}k\nn={c:,}", ha="center", va="bottom", color=INK2, fontsize=8)
        ax.yaxis.set_major_formatter(SGD)
        ax.set_ylabel("Median resale price (SGD)")
        ax.set_ylim(0, s["p75_price"].max() * 1.2)
        ax.grid(axis="x", visible=False)
    return _finish(fig, ax, title, subtitle, path)


def effect_panels(raw: pd.DataFrame, adj: pd.DataFrame, x_col: str, path: Path, title: str,
                  subtitle: str, xlabel: str) -> Path:
    """Left: raw median by band. Right: adjusted % effect vs reference band (same bands)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4))
    a1.plot(raw[x_col], raw["median_price"], color=ORANGE, marker="o", markersize=5)
    a1.yaxis.set_major_formatter(SGD)
    a1.set_title("Raw median price (not adjusted)", fontsize=10, pad=6)
    a1.set_xlabel(xlabel)
    a2.axhline(0, color=MUTED, linewidth=0.8)
    a2.fill_between(adj[x_col], adj["ci_low"], adj["ci_high"], color=BLUE, alpha=0.15, linewidth=0)
    a2.plot(adj[x_col], adj["pct_vs_reference"], color=BLUE, marker="o", markersize=5)
    a2.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    a2.set_title("Adjusted difference vs lowest band (95% CI)", fontsize=10, pad=6)
    a2.set_xlabel(xlabel)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.01, 0.905, subtitle, color=INK2, fontsize=9)
    fig.text(0.01, 0.005, SOURCE_NOTE, color=MUTED, fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def mix_lines(mix: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    series = [("share_pct_3 ROOM", "3 ROOM", ORANGE), ("share_pct_4 ROOM", "4 ROOM", BLUE),
              ("share_pct_5 ROOM", "5 ROOM", AQUA)]
    for col, name, color in series:
        ax.plot(mix["year"], mix[col], color=color, marker="o", markersize=4)
    # End labels, nudged apart so close values (e.g. 3 and 5 ROOM) never overlap.
    ends = sorted(((mix[c].iloc[-1], n) for c, n, _ in series))
    placed: list[float] = []
    for val, name in ends:
        y = val if not placed else max(val, placed[-1] + 1.6)
        placed.append(y)
        ax.annotate(f"{name}  {val:.1f}%", (mix["year"].iloc[-1], val), xytext=(mix["year"].iloc[-1] + 0.15, y),
                    textcoords="data", va="center", color=INK, fontsize=9)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_ylabel("Share of transactions")
    ax.set_xlim(mix["year"].min() - 0.3, mix["year"].max() + 1.3)
    ax.set_xticks(mix["year"])
    return _finish(fig, ax, "Has the mix of flats sold changed?",
                   f"Share of each year's transactions, three largest flat types; "
                   f"{int(mix['year'].max())} is a part-year (full months to date)", path)
