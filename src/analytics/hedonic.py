"""Hedonic regression (M1/M2) and the mix-adjusted (time-dummy) price index.

Purpose
    Estimates how log resale price varies with observable characteristics while
    holding the transaction month fixed. Used for H1-H3 (characteristic premiums),
    supporting evidence for H4 (town effects after controls), and H5 (mix-adjusted
    price change). Specification and rationale: docs/HYPOTHESIS_REGISTER.md §1.

Model
    M1: log(price) ~ C(month) + C(town) + C(flat_type) + C(flat_model)
                     + floor_area_sqm + storey_mid + remaining_lease_years
    M2: same, but storey as C(storey_range) and lease as C(5-year lease band).

    Standard errors are cluster-robust by building (block + street). Coefficients
    are log-points; ``pct_effect`` converts a coefficient x contrast to a %.

Why statsmodels OLS rather than scikit-learn
    We need inference (cluster-robust covariance, CIs, Wald tests), which
    statsmodels provides; scikit-learn is used for prediction in Phase 3.

Memory note
    The full-period design matrix is ~240k x ~175 float64 (~340 MB); this fits
    comfortably on an 8 GB machine.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.outliers_influence import variance_inflation_factor

M1_FORMULA = ("log_price ~ C(month) + C(town) + C(flat_type) + C(flat_model)"
              " + floor_area_sqm_num + storey_mid + remaining_lease_years")
M2_FORMULA = ("log_price ~ C(month) + C(town) + C(flat_type) + C(flat_model)"
              " + floor_area_sqm_num + C(storey_range) + C(lease_band)")

LEASE_BAND_WIDTH = 5


def add_lease_band(df: pd.DataFrame) -> pd.DataFrame:
    """5-year remaining-lease bands, e.g. '70-74'. Lower bound = floor(years / 5) * 5."""
    lo = (np.floor(df["remaining_lease_years"] / LEASE_BAND_WIDTH) * LEASE_BAND_WIDTH).astype(int)
    out = df.copy()
    out["lease_band"] = lo.astype(str).str.zfill(2) + "-" + (lo + LEASE_BAND_WIDTH - 1).astype(str).str.zfill(2)
    return out


def fit(df: pd.DataFrame, formula: str = M1_FORMULA) -> RegressionResultsWrapper:
    """Fit OLS with building-clustered standard errors."""
    groups = pd.factorize(df["building"])[0]
    # Known, harmless rank deficiency: flat_type MULTI-GENERATION and flat_model
    # "Multi Generation" label the same flats, so only their sum is identified.
    # Tested terms (area, storey, lease, month effects) remain estimable (DEC-016).
    import warnings
    from statsmodels.tools.sm_exceptions import SingularMatrixWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SingularMatrixWarning)
        return smf.ols(formula, data=df).fit(cov_type="cluster", cov_kwds={"groups": groups})


def pct_effect(res: RegressionResultsWrapper, term: str, contrast: float) -> dict[str, float]:
    """% price difference for `contrast` units of `term`, with 95% CI and one-sided p (>0)."""
    beta = res.params[term]
    lo, hi = res.conf_int().loc[term]
    z = res.tvalues[term]
    from scipy import stats
    return {
        "coef": float(beta),
        "se": float(res.bse[term]),
        "pct": float(100 * np.expm1(beta * contrast)),
        "pct_ci_low": float(100 * np.expm1(lo * contrast)),
        "pct_ci_high": float(100 * np.expm1(hi * contrast)),
        "p_two_sided": float(res.pvalues[term]),
        "p_one_sided_positive": float(stats.norm.sf(z)),
    }


def categorical_effects(res: RegressionResultsWrapper, var: str) -> pd.DataFrame:
    """% difference of each level of C(var) vs its reference level, with 95% CI."""
    prefix = f"C({var})[T."
    rows = []
    ci = res.conf_int()
    for name in res.params.index:
        if name.startswith(prefix):
            rows.append({
                "level": name[len(prefix):-1],
                "pct_vs_reference": 100 * np.expm1(res.params[name]),
                "ci_low": 100 * np.expm1(ci.loc[name, 0]),
                "ci_high": 100 * np.expm1(ci.loc[name, 1]),
            })
    return pd.DataFrame(rows)


def reference_level(df: pd.DataFrame, var: str) -> str:
    """patsy uses the first sorted level as the reference."""
    return sorted(df[var].dropna().unique())[0]


@dataclass
class Diagnostics:
    n: int
    n_clusters: int
    r2: float
    resid_skew: float
    resid_kurtosis_excess: float
    resid_sd_by_fitted_decile: list[float]
    vif: dict[str, float]
    design_columns: int
    design_rank: int


def diagnostics(res: RegressionResultsWrapper, df: pd.DataFrame,
                numeric_terms: tuple[str, ...] = ("floor_area_sqm_num", "storey_mid", "remaining_lease_years")
                ) -> Diagnostics:
    from scipy import stats
    resid = res.resid
    deciles = pd.qcut(res.fittedvalues, 10, labels=False)
    sd_by_decile = resid.groupby(deciles).std().round(4).tolist()
    exog = res.model.exog
    names = res.model.exog_names
    # The design is rank-deficient by one column: flat_type MULTI-GENERATION and
    # flat_model "Multi Generation" label the same flats (DEC-016). VIF regressions
    # are still valid (OLS fitted values are unique), so the warning is silenced.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vif = {t: float(variance_inflation_factor(exog, names.index(t))) for t in numeric_terms if t in names}
    return Diagnostics(
        n=int(res.nobs), n_clusters=int(df["building"].nunique()), r2=float(res.rsquared),
        resid_skew=float(stats.skew(resid)), resid_kurtosis_excess=float(stats.kurtosis(resid)),
        resid_sd_by_fitted_decile=sd_by_decile, vif=vif,
        design_columns=int(exog.shape[1]), design_rank=int(np.linalg.matrix_rank(exog)),
    )


def month_index(res: RegressionResultsWrapper, months: list[str]) -> pd.DataFrame:
    """Mix-adjusted monthly index: exp(month coefficient), base month = 1.0 (first month)."""
    coefs = {months[0]: 0.0}
    for m in months[1:]:
        coefs[m] = float(res.params[f"C(month)[T.{m}]"])
    return pd.DataFrame({"month": list(coefs), "log_index": list(coefs.values())}).assign(
        index=lambda d: np.exp(d["log_index"]))


def period_change(res: RegressionResultsWrapper, months: list[str],
                  base_months: list[str], comp_months: list[str]) -> dict[str, float]:
    """Change in mean exp(month effect) between two periods, delta-method 95% CI.

    L_P = mean_{m in P} exp(g_m) (g_base_month = 0, fixed);  R = L_comp / L_base.
    dR/dg_m = exp(g_m)/(n_comp * L_base)           for m in comp
            = -L_comp * exp(g_m)/(n_base * L_base^2) for m in base
    """
    names = {m: f"C(month)[T.{m}]" for m in months[1:]}
    g = {m: (0.0 if m == months[0] else float(res.params[names[m]])) for m in months}
    L_b = np.mean([np.exp(g[m]) for m in base_months])
    L_c = np.mean([np.exp(g[m]) for m in comp_months])
    R = L_c / L_b
    terms = [names[m] for m in months[1:]]
    grad = pd.Series(0.0, index=terms)
    for m in comp_months:
        if m != months[0]:
            grad[names[m]] += np.exp(g[m]) / (len(comp_months) * L_b)
    for m in base_months:
        if m != months[0]:
            grad[names[m]] -= L_c * np.exp(g[m]) / (len(base_months) * L_b ** 2)
    cov = res.cov_params().loc[terms, terms]
    se = float(np.sqrt(grad.values @ cov.values @ grad.values))
    return {"ratio": float(R), "pct": 100 * (R - 1), "pct_ci_low": 100 * (R - 1.96 * se - 1),
            "pct_ci_high": 100 * (R + 1.96 * se - 1), "se_ratio": se}
