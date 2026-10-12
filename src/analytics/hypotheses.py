"""Execute pre-registered hypotheses H1-H5 (docs/HYPOTHESIS_REGISTER.md).

Every threshold, contrast and decision rule here mirrors the register, which
was committed before this code was run. Changing any constant below requires
a DECISION_LOG entry explaining why (to prevent tuning towards significance).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from src.analytics import hedonic as H
from src.analytics.common import MIN_SEGMENT_N

PRACTICAL_PCT = 2.0          # % of price, for the stated contrast (H1-H3)
PRACTICAL_EPSILON_SQ = 0.06  # H4 effect-size threshold
ALPHA = 0.05
CONTRASTS = {  # hypothesis -> (model term, contrast size, unit label)
    "H1": ("storey_mid", 10, "+10 floors"),
    "H2": ("remaining_lease_years", 10, "+10 years remaining lease"),
    "H3": ("floor_area_sqm_num", 10, "+10 sqm floor area"),
}
H5_BOOTSTRAP = 1000


@dataclass
class HypothesisOutputs:
    results: pd.DataFrame
    robustness: pd.DataFrame
    details: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)


def _decide_coef(p_adj: float, pct: float, lo: float, hi: float) -> str:
    if p_adj >= ALPHA or pct <= 0:
        return "Not supported"
    if lo >= PRACTICAL_PCT:
        return "Supported"
    if hi < PRACTICAL_PCT:
        return "Not supported (association real but below practical threshold)"
    return "Inconclusive (significant, but CI spans practical threshold)"


def _band_slope(effects: pd.DataFrame, ref_value: float, ref_n: int, x_col: str, counts: pd.Series,
                contrast: float) -> float:
    """Weighted linear slope of binned % effects on bin midpoint -> implied % per contrast.

    Used to express the binned robustness model (M2) on the same scale as M1.
    Fitted on log effects so it is comparable with the M1 log-linear coefficient.
    """
    x = np.r_[ref_value, effects[x_col].to_numpy(float)]
    y = np.r_[0.0, np.log1p(effects["pct_vs_reference"].to_numpy(float) / 100)]
    w = np.r_[ref_n, effects["level"].map(counts).to_numpy(float)]
    slope = np.polyfit(x, y, 1, w=np.sqrt(w))[0]
    return float(100 * np.expm1(slope * contrast))


def m2_implied_effects(res_m2, df: pd.DataFrame) -> dict[str, float]:
    storey = H.categorical_effects(res_m2, "storey_range")
    storey["mid"] = storey["level"].str.slice(0, 2).astype(int) + 1
    s_counts = df["storey_range"].value_counts()
    s_ref = H.reference_level(df, "storey_range")
    lease = H.categorical_effects(res_m2, "lease_band")
    lease["mid"] = lease["level"].str.slice(0, 2).astype(int) + 2.5
    l_counts = df["lease_band"].value_counts()
    l_ref = H.reference_level(df, "lease_band")
    return {
        "H1": _band_slope(storey, int(s_ref[:2]) + 1, s_counts[s_ref], "mid", s_counts, 10),
        "H2": _band_slope(lease, int(l_ref[:2]) + 2.5, l_counts[l_ref], "mid", l_counts, 10),
        "_storey_bands": storey, "_lease_bands": lease,
    }


def run_h1_h4(recent: pd.DataFrame, full: pd.DataFrame, fits: dict) -> tuple[list[dict], list[dict], dict]:
    m1 = fits["m1_recent"]
    rows, robust, details = [], [], {}
    m2_eff = m2_implied_effects(fits["m2_recent"], recent)
    details["m2_storey_bands"] = m2_eff["_storey_bands"]
    details["m2_lease_bands"] = m2_eff["_lease_bands"]

    for hid, (term, contrast, label) in CONTRASTS.items():
        e = H.pct_effect(m1, term, contrast)
        rows.append({"hypothesis": hid, "contrast": label, "method": "Hedonic OLS M1, building-clustered SE",
                     "population": "recent window", "n": int(m1.nobs), "estimate_pct": e["pct"],
                     "ci_low_pct": e["pct_ci_low"], "ci_high_pct": e["pct_ci_high"],
                     "p_raw": e["p_one_sided_positive"], "effect_size_metric": "% price difference",
                     "practical_threshold": PRACTICAL_PCT})
        for spec, res in [("M1 full period", fits["m1_full"]), ("M1 excl. retained duplicates", fits["m1_nodup"])]:
            r = H.pct_effect(res, term, contrast)
            robust.append({"hypothesis": hid, "specification": spec, "estimate_pct": r["pct"],
                           "ci_low_pct": r["pct_ci_low"], "ci_high_pct": r["pct_ci_high"], "n": int(res.nobs)})
        if hid in m2_eff:
            robust.append({"hypothesis": hid, "specification": "M2 binned (implied slope)",
                           "estimate_pct": m2_eff[hid], "ci_low_pct": np.nan, "ci_high_pct": np.nan,
                           "n": int(fits["m2_recent"].nobs)})

    # H4: Kruskal-Wallis on 4-ROOM prices across towns
    four = recent.loc[recent["flat_type"] == "4 ROOM"]
    counts = four["town"].value_counts()
    keep = counts[counts >= MIN_SEGMENT_N].index
    excluded = sorted(counts[counts < MIN_SEGMENT_N].index)
    groups = [g["resale_price_sgd"].to_numpy() for _, g in four[four["town"].isin(keep)].groupby("town")]
    n4 = int(sum(len(g) for g in groups))
    h_stat, p_kw = stats.kruskal(*groups)
    eps2 = float(h_stat / (n4 - 1))
    med = four[four["town"].isin(keep)].groupby("town")["resale_price_sgd"].median()
    town_eff = H.categorical_effects(m1, "town")
    town_eff = pd.concat([town_eff, pd.DataFrame([{"level": H.reference_level(recent, "town"),
                                                   "pct_vs_reference": 0.0, "ci_low": 0.0, "ci_high": 0.0}])])
    details["h4"] = {"kruskal_H": float(h_stat), "towns_tested": int(len(keep)), "towns_excluded_lt30": excluded,
                     "median_ratio_max_min": float(med.max() / med.min()), "highest_median_town": med.idxmax(),
                     "lowest_median_town": med.idxmin(), "highest_median": float(med.max()),
                     "lowest_median": float(med.min()),
                     "adjusted_town_effect_range_pct": float(town_eff["pct_vs_reference"].max()
                                                             - town_eff["pct_vs_reference"].min())}
    details["town_effects_m1"] = town_eff.sort_values("pct_vs_reference")
    rows.append({"hypothesis": "H4", "contrast": "4-ROOM price distribution across towns",
                 "method": "Kruskal-Wallis; effect size epsilon-squared", "population": "recent window, 4 ROOM",
                 "n": n4, "estimate_pct": np.nan, "ci_low_pct": np.nan, "ci_high_pct": np.nan,
                 "p_raw": float(p_kw), "effect_size_metric": "epsilon-squared", "effect_size": eps2,
                 "practical_threshold": PRACTICAL_EPSILON_SQ})

    # Holm across H1-H4
    p_adj = multipletests([r["p_raw"] for r in rows], alpha=ALPHA, method="holm")[1]
    for r, pa in zip(rows, p_adj):
        r["p_holm"] = float(pa)
        if r["hypothesis"] == "H4":
            r["status"] = "Supported" if (pa < ALPHA and r["effect_size"] >= PRACTICAL_EPSILON_SQ) else "Not supported"
        else:
            r["status"] = _decide_coef(pa, r["estimate_pct"], r["ci_low_pct"], r["ci_high_pct"])
            same = [x for x in robust if x["hypothesis"] == r["hypothesis"]]
            clears = [(x["estimate_pct"] >= PRACTICAL_PCT) == (r["estimate_pct"] >= PRACTICAL_PCT)
                      and np.sign(x["estimate_pct"]) == np.sign(r["estimate_pct"]) for x in same]
            r["robust"] = bool(all(clears))
    return rows, robust, details


def run_h5(full: pd.DataFrame, m1_full, months: list[str], base_months: list[str],
           comp_months: list[str], seed: int) -> dict:
    adj = H.period_change(m1_full, months, base_months, comp_months)
    base = full.loc[full["month"].isin(base_months), "resale_price_sgd"].to_numpy()
    comp = full.loc[full["month"].isin(comp_months), "resale_price_sgd"].to_numpy()
    raw = 100 * (np.median(comp) / np.median(base) - 1)
    rng = np.random.default_rng(seed)
    boots = np.empty(H5_BOOTSTRAP)
    for i in range(H5_BOOTSTRAP):
        boots[i] = 100 * (np.median(rng.choice(comp, comp.size)) / np.median(rng.choice(base, base.size)) - 1)
    raw_lo, raw_hi = np.percentile(boots, [2.5, 97.5])
    diff = raw - adj["pct"]
    overlap = not (raw_lo > adj["pct_ci_high"] or raw_hi < adj["pct_ci_low"])
    if abs(diff) >= 2 and not overlap:
        status = "Material composition effect"
    elif abs(diff) >= 2:
        status = "Inconclusive"
    else:
        status = "No material composition effect"
    return {"hypothesis": "H5", "base_period": f"{base_months[0]} to {base_months[-1]}",
            "comparison_period": f"{comp_months[0]} to {comp_months[-1]}",
            "raw_median_base": float(np.median(base)), "raw_median_comparison": float(np.median(comp)),
            "raw_change_pct": float(raw), "raw_ci_low": float(raw_lo), "raw_ci_high": float(raw_hi),
            "mix_adjusted_change_pct": adj["pct"], "adj_ci_low": adj["pct_ci_low"], "adj_ci_high": adj["pct_ci_high"],
            "difference_pp": float(diff), "cis_overlap": overlap, "n_base": int(base.size),
            "n_comparison": int(comp.size), "status": status}
