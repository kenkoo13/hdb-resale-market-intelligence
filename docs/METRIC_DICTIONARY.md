# Metric Dictionary

Definitions of every engineered field, business metric, statistical measure and model metric.
**Layer** says where each one is calculated. A metric computed in more than one layer (for example, Python and DAX) must give the same result, and its validation entry says how that was checked.

Types: **D** descriptive, **I** inferential, **P** predictive.

## 1. Row-level derived fields (Phase 1, Python: `src/transformation/clean.py`)

### Price per square metre — `price_per_sqm_sgd`
- **Definition:** The resale price divided by the approximate floor area.
- **Formula:** `resale_price_sgd / floor_area_sqm_num`
- **Unit / grain:** SGD per sqm, per transaction. Type D.
- **Source fields:** `resale_price`, `floor_area_sqm`.
- **Missing or invalid:** Never null in the clean table. Both inputs are required, and a floor area ≤ 0 is quarantined.
- **Interpretation and limits:** Useful for comparing flats of different sizes. The floor area includes recesses, upgrading additions and roof terraces (publisher's note), and price per sqm does not scale linearly with size (small flats usually cost more per sqm). Compare within a flat type, not across types.
- **Validation:** `tests/test_clean.py::test_derived_fields`.

### Storey midpoint — `storey_mid`
- **Definition:** The midpoint of the three-storey band, for example `10 TO 12` → 11.
- **Formula:** `(storey_lower + storey_upper) / 2`
- **Unit / grain:** floor, per transaction. Type D.
- **Interpretation and limits:** An approximation, since the exact floor is not published. It preserves the ordering between bands.
- **Validation:** `tests/test_parsers.py::test_parse_storey_range`.

### Remaining lease (years) — `remaining_lease_years`
- **Definition:** The lease remaining at the time of sale, as recorded by HDB.
- **Formula:** `(years × 12 + months) / 12`, parsed from the text. `"N years"` is read as 0 months.
- **Unit / grain:** years (decimal), per transaction. Type D.
- **Missing or invalid:** Unparseable text → null plus `flag_invalid_remaining_lease`. There were 0 such rows in the 2026-10-12 snapshot.
- **Interpretation:** The preferred lease variable (DEC-012).
- **Validation:** `tests/test_parsers.py::test_parse_remaining_lease_formats`.

### Derived remaining lease (consistency check only) — `derived_remaining_lease_years`
- **Formula:** `99 − ((year − lease_commence_year) + (month_number − 1) / 12)`
- **Assumptions:** A 99-year lease starting on 1 January of `lease_commence_year`. The actual start month is unknown, so this value can be up to about one year *below* the source value.
- **Use:** Only to flag `|remaining_lease_years − derived| > 1.5` (`flag_lease_inconsistent`). It is **not** used as a feature.
- **Validation:** `tests/test_clean.py::test_derived_fields` and `test_lease_inconsistency_flagged`. On the real data the observed discrepancy has a median of 0.50 years and a 99th percentile of 1.00.

### Partial-month flag — `is_partial_month`
- **Formula:** `month_date ≥ first day of the retrieval month (Asia/Singapore)`
- **Use:** Rows where this is true are excluded from monthly trend statistics, hypothesis tests and model training or evaluation (DEC-008).

### Duplicate group size — `duplicate_group_size`
- **Formula:** The number of retained clean rows sharing all 11 normalised source fields.
- **Use:** Annotation and sensitivity analysis (DEC-013).

## 2. Business metrics (Phase 2, Python: `src/analytics/descriptive.py`)

All of these are computed on analysis-ready rows: clean rows, excluding the partial month, unless the table states otherwise. Each one is reported with `transactions`, the count of rows in the group.

| Metric | Definition / formula | Type | Notes |
|---|---|---|---|
| Transactions | Count of rows in the group | D | Registered resales; the partial month is shown flagged in `monthly_market.csv` |
| Median price | 50th percentile of `resale_price_sgd` (pandas `median`) | D | The headline "typical price" (DEC-015) |
| P25 / P75 price, IQR | 25th / 75th percentiles (pandas `quantile`, linear interpolation); IQR = P75 − P25 | D | The middle 50% of prices. Shows spread, not error. |
| Mean price | Arithmetic mean | D | Reported for comparison only. Skewed upward. |
| Median price per sqm | Median of row-level `price_per_sqm_sgd`, **not** median price ÷ median area | D | Compare within a flat type |
| Low sample | `transactions < 30` | D | A threshold where medians become unstable. It is a conventional rule of thumb, not a derived cut-off. |
| Skewness | Fisher–Pearson coefficient (`scipy.stats.skew`) | D | > 0 means a long right tail |
| Floor area band | Left-closed bands: <50, 50–69, 70–89, 90–109, 110–129, 130–149, 150+ sqm | D | |
| Remaining lease band | `floor(years/5)×5` to +4, for example `70-74` | D | |
| Flat-type share | Transactions of a type ÷ all transactions in the year × 100 | D | `mix_over_time.csv` |

## 3. Statistical measures (Phase 2, Python: `src/analytics/hedonic.py`, `hypotheses.py`)

| Measure | Formula | Type | Interpretation and limits |
|---|---|---|---|
| Hedonic coefficient β | OLS on `log(price)`; see DEC-016 | I | The average log-price difference per unit, holding the other model terms fixed. An association, not a causal effect. |
| % effect for a contrast Δ | `100 × (exp(β·Δ) − 1)`; CI by transforming the β CI | I | For example, Δ = 10 floors |
| Cluster-robust SE | Sandwich estimator clustered by building | I | Allows correlation within buildings and unequal variance |
| One-sided p (H1–H3) | `1 − Φ(β / SE)` | I | Direction pre-specified as positive |
| Holm-adjusted p | Holm–Bonferroni step-down across H1–H4 | I | Controls the family-wise error rate at 5% |
| Kruskal–Wallis H | Rank-based test of several groups (`scipy.stats.kruskal`) | I | Assumes independence, which is violated within buildings, so the p-value is optimistic |
| ε² (epsilon-squared) | `H / (n − 1)` | I | The share of rank variation explained by the groups. 0.01 / 0.06 / 0.14 are conventional small / medium / large benchmarks. |
| Mix-adjusted index | `100 × exp(γ_m) / mean_{m∈2017} exp(γ_m)`, where γ_m are the M1 month coefficients (full period) | I | Price level of comparable flats (DEC-017) |
| Mix-adjusted period change | `L_comp / L_base − 1`, with `L_P = mean_{m∈P} exp(γ_m)`; 95% CI by the delta method | I | Formula and gradient documented in `hedonic.period_change` |
| Raw median change | `median(prices in comp) / median(prices in base) − 1`; 95% CI from a percentile bootstrap (1,000 resamples, seed 42) | D/I | Mixes price change with composition change |
| Composition effect | Raw change − mix-adjusted change (percentage points) | D | Negative means the raw median understates price growth for comparable flats |
| VIF | `1 / (1 − R²_j)` from regressing predictor j on all other columns | Diagnostic | Values above 10 signal high collinearity |

## 4. Model evaluation metrics (Phase 3, Python: `src/modelling/evaluate.py`)

These are all *predictive* (type P) and are computed on held-out rows. y is the actual price and ŷ the estimate, both in SGD.

| Metric | Formula | Unit | Interpretation and limits |
|---|---|---|---|
| **MAE** (primary) | `mean(|y − ŷ|)` | SGD | Average dollar miss. Robust, interpretable. |
| RMSE | `sqrt(mean((y − ŷ)²))` | SGD | Penalises large misses more. RMSE much greater than MAE means occasional big errors. |
| R² | `1 − Σ(y − ŷ)² / Σ(y − ȳ)²` | — | Share of price variance explained. Can be negative when a model is worse than predicting the mean. |
| MedAE | `median(|y − ŷ|)` | SGD | The typical miss for a "middle" transaction |
| MdAPE | `100 × median(|y − ŷ| / y)` | % | The typical miss as a share of price. This is how buyers think about error. |
| Median bias | `100 × median((ŷ − y) / y)` | % | > 0 means the model tends to over-estimate. Shows drift when the market moves after training. |
| 80% interval | `[ŷ·exp(q₁₀), ŷ·exp(q₉₀)]`, where q are the 10th and 90th percentiles of `log(y) − log(ŷ)` on the **validation** set (split conformal) | SGD | Intended to contain 80% of actual prices. **Valid only if test errors look like validation errors.** Coverage is measured on test. |
| Coverage | Share of test rows with `low ≤ y ≤ high` | % | Compared against the nominal 80% |
| Permutation importance | Increase in test MAE when one feature's values are shuffled (5 repeats, 5,000-row test sample) | SGD | How much the model *relies* on a feature. It is not a causal effect, and correlated features share importance. |
| Reliability label | `n < 30` test rows in a segment → "less reliable" | — | Same threshold as the descriptive tables |

**Baselines:**
- **B0:** the training median.
- **B1:** the town × flat-type training median (falling back to flat type, then global; a segment needs n ≥ 30).
- **B2:** the same as B1, using only the last 12 training months.

## 5. DAX measures (Phase 4, Power BI)

The full catalogue of 37 measures, with formula, format, filter-context notes and validation results, is in [BI_BUILD_GUIDE.md §4](BI_BUILD_GUIDE.md#4-dax-measures). It is generated from `src/reporting/build_pbip.py`, the single source of truth.

DAX measures reproduce, and do not redefine, the Python metrics:
- `Median Price` = §2 median price;
- `P25 Price` / `P75 Price` = §2 (`PERCENTILE.INC` = pandas linear quantile);
- the *Latest 12M* measures use the same window as the Python latest 12 months.

13 measure values were verified equal to the Python results on 2026-10-12. Model and evidence measures display pre-computed Python values; they are not recalculated in DAX.
