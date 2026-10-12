# Hypothesis Register

## 0. Pre-registration statement

The hypotheses, methods, thresholds and decision rules in §1–§2 were written and **committed to Git before any of the tests below were run** (see the commit history of this file). Results are added in §3 only after execution.

**What had already been seen:** the Phase 1 data-quality profile. That covers row counts, field formats, value ranges, category counts and duplicates, plus the overall median price of SGD 505,000. No price comparison by storey, lease, floor area, town or time had been computed. The expected directions below therefore come from general housing-market reasoning, not from this dataset's results.

**Nature of the evidence:** this is observational data. Every hypothesis concerns **association conditional on observed characteristics**, not causation. Unobserved factors such as exact location, view, renovation condition, distance to transport, and buyer and seller circumstances can confound every estimate.

## 1. Common design

| Element | Definition |
|---|---|
| Unit of analysis | One registered resale transaction (a row of `transactions_clean`) |
| Base population | Clean rows with `is_partial_month = False` (DEC-008); Q07 artefact rows are already excluded (DEC-013) |
| **Recent window (H1–H4)** | The **24 full months ending with the last full month** of the snapshot (for the 2026-10-12 snapshot: 2024-10 to 2026-09). This is the market most relevant to current users and keeps the price level roughly comparable. |
| Full period (H5, and robustness for H1–H3) | All full months, 2017-01 to the last full month |
| Outcome | `log(resale_price_sgd)`. Prices are right-skewed, and effects on a log scale read as percentages. |
| Hedonic model (M1) | OLS: `log(price) ~ C(month) + C(town) + C(flat_type) + C(flat_model) + floor_area_sqm + storey_mid + remaining_lease_years`. The month fixed effects absorb market-wide price movements, so the other coefficients are *within-month* comparisons. |
| Standard errors | **Cluster-robust by building** (`block` + `street_name`). Sales in the same building share unobserved location and quality, so treating them as independent would overstate precision. This also handles heteroskedasticity. |
| Effect expression | For coefficient β and contrast Δ, the % difference is `100 × (exp(β·Δ) − 1)`, with a 95% CI from the cluster-robust CI of β |
| Practical significance | **2% of price** for the stated contrast. At the recent median (around SGD 500k–600k) that is about SGD 10,000–12,000. This is the order of magnitude a buyer would treat as material when comparing flats, and well above rounding in the price data. It was chosen before any results were seen. |
| Multiple testing | H1–H4 are four confirmatory tests. Their p-values are **Holm–Bonferroni** adjusted at a family-wise α = 0.05. H5 is an estimation question, not a significance test. |
| Decision rule (H1–H3) | **Supported:** Holm-adjusted p < 0.05, the expected direction, *and* the lower 95% CI bound ≥ the practical threshold. **Inconclusive:** significant in the expected direction but the CI straddles the threshold. **Not supported:** not significant, wrong direction, or the upper CI bound < the threshold (real but too small to matter). |
| Assumption checks (M1) | Residual skewness and kurtosis; residual spread versus fitted values; VIF for the three numeric predictors; linearity checked by refitting with storey bands and 5-year lease bands as categories (robustness spec M2). |
| Robustness | (a) M2 binned specification; (b) the same model on the full period; (c) excluding retained exact-duplicate rows. A conclusion is reported as *robust* only if (a)–(c) agree in direction and in whether the threshold is cleared. |
| Large-sample caveat | With about 50,000+ rows almost any non-zero effect is "significant". **Effect sizes and practical thresholds, not p-values, carry the interpretation.** |

## 2. Hypotheses

### H1 — Storey level
- **Business question:** Do flats on higher floors sell for more than otherwise comparable flats?
- **H0:** β_storey = 0 in M1. **H1:** β_storey > 0.
- **Expected direction (pre-specified):** positive (views, light, less noise).
- **Variable:** `storey_mid` (midpoint of the three-storey band). **Contrast:** +10 floors.
- **Population:** recent window, all flat types.
- **Method:** M1 coefficient. Chosen because it compares flats within the same month, town, flat type and model and with the same area and lease. The raw medians by storey band are reported alongside to show how unadjusted comparisons can mislead, since tall blocks are concentrated in particular towns and eras.
- **Practical threshold:** ≥ 2% for +10 floors.
- **Confounders and limitations:** the storey band is coarse; there is no data on view or facing; high storeys may coincide with newer, better-located blocks *within* a town.

### H2 — Remaining lease
- **Business question:** Holding other observable characteristics fixed, do flats with more lease remaining sell for more?
- **H0:** β_lease = 0 in M1. **H1:** β_lease > 0.
- **Expected direction (pre-specified):** positive (a longer remaining lease means more years of use and better financing eligibility).
- **Variable:** `remaining_lease_years` (source value, DEC-012). **Contrast:** +10 years.
- **Population:** recent window.
- **Practical threshold:** ≥ 2% for +10 years.
- **Confounders and limitations:** lease is strongly tied to building age, design era and upgrading, which are partly but not fully captured by flat model. The estimate mixes the "lease" effect with the "age and condition" effect. A linear term may misrepresent a curved relationship, which M2 checks.

### H3 — Floor area within flat type
- **Business question:** Among flats of the same type, do larger flats sell for more?
- **H0:** β_area = 0 in M1. **H1:** β_area > 0.
- **Expected direction (pre-specified):** positive.
- **Variable:** `floor_area_sqm`. **Contrast:** +10 sqm.
- **Population:** recent window.
- **Practical threshold:** ≥ 2% for +10 sqm.
- **Confounders and limitations:** floor area includes recesses and roof terraces (publisher's note); within a type, larger area often means an older design, which works in the opposite direction through lease.

### H4 — Town differences for like-for-like flats
- **Business question:** For the same flat type, do prices differ materially between towns?
- **H0:** the distribution of resale prices for **4-ROOM** flats is the same in every town. **H1:** at least one town's distribution differs.
- **Expected direction:** none (two-sided omnibus).
- **Population:** recent window, `flat_type = 4 ROOM`. This is the most common type, so most towns have adequate samples. Towns with fewer than 30 4-ROOM sales in the window are excluded from the test and listed.
- **Method:** **Kruskal–Wallis** test, a rank-based comparison of several groups. It does not assume normal prices, which are skewed, or equal variances in the normal-theory sense. Effect size: **ε² (epsilon-squared) = H / (n − 1)**, the share of rank variation explained by town.
- **Practical threshold:** ε² ≥ 0.06, the conventional "medium" benchmark for η²-type measures. Supporting descriptive: the ratio of the highest to the lowest town median.
- **Supporting evidence (not part of the decision rule):** the spread of town coefficients in M1, which shows whether differences persist after controlling for area, storey, lease and model.
- **Assumptions:** independent observations (violated within buildings, so p-values are optimistic; the effect size is the main evidence); ordinal outcome (satisfied).
- **Decision rule:** Supported if Holm-adjusted p < 0.05 and ε² ≥ 0.06; Not supported otherwise.

### H5 — How much of the headline price change is a change in the mix of flats sold? (estimation question)
- **Business question:** Does the change in the *raw* median resale price give a fair picture of how much prices for comparable flats changed?
- **Quantities:**
  - **Raw change:** median price in the latest 12 full months ÷ median price in 2017 − 1.
  - **Mix-adjusted change:** the change in a hedonic time-dummy index over the same periods. M1 is fitted on the full period, and each period's level is the mean of exp(month coefficients), normalised so 2017 = 100.
- **Expected direction:** not pre-specified. Composition could raise or lower the raw median.
- **Method:** a hedonic time-dummy index, a standard way to measure price change for comparable properties, because it holds flat characteristics fixed. CIs: a bootstrap for the raw median change (1,000 resamples, seed 42) and a cluster-robust delta method for the index change.
- **Material difference:** the raw and mix-adjusted changes differ by ≥ 2 percentage points **and** their 95% CIs do not overlap. This is a deliberately conservative criterion.
- **Status categories:** *Material composition effect*, *No material composition effect*, or *Inconclusive* (difference ≥ 2 pp but the CIs overlap).
- **Limitations:** the index assumes the characteristic premiums in M1 are constant over time. Unobserved quality changes, such as renovation and newer designs within a model label, remain in the index.

### Exploratory (not confirmatory; not used in the Holm family)
- E1: Price differences by flat model after controls, from the M1 coefficients.
- E2: The shape of the lease relationship, from the M2 bins.
- E3: Months and segments with thin data (cells with fewer than 30 sales).
Exploratory observations are labelled as such and are not presented as tested findings.

## 3. Results (executed 2026-10-12, snapshot `20261012T010041Z`)

Source of every number: `outputs/tables/analysis_results.json`, `hypothesis_results.csv`, `hypothesis_robustness.csv`, `h5_composition.csv`, produced by `python -m src.analytics.run_analysis`.

**Populations as executed:**
- Recent window: 2024-10 to 2026-09, 50,902 transactions in 9,197 buildings.
- Full period: 2017-01 to 2026-09, 241,557 transactions in 9,754 buildings.
- Latest 12 months: 2025-10 to 2026-09, 24,658 transactions.

**Deviations from the pre-registered plan:** none in hypotheses, populations, thresholds or decision rules. One implementation fact surfaced and is documented, not changed:
- The design matrix has rank 77 of 78 columns. Flat type `MULTI-GENERATION` and flat model `Multi Generation` are the same 11 flats in the window, so only the *sum* of those two coefficients is identified.
- A rank check confirmed that floor area, storey, remaining lease and all month effects are uniquely estimable, so H1–H3 and H5 are unaffected (DEC-016).

### Summary

| ID | Contrast | Estimate | 95% CI | Holm p | Threshold | Status | Robust |
|---|---|---:|---|---:|---|---|---|
| H1 | +10 floors | **+7.8%** | 7.5% to 8.0% | < 0.001 | ≥ 2% | **Supported** | Yes |
| H2 | +10 years remaining lease | **+10.6%** | 10.3% to 10.9% | < 0.001 | ≥ 2% | **Supported** | Yes |
| H3 | +10 sqm, same flat type | **+9.3%** | 8.9% to 9.7% | < 0.001 | ≥ 2% | **Supported** | Yes |
| H4 | 4-ROOM prices across 26 towns | **ε² = 0.42** | — | < 0.001 | ε² ≥ 0.06 | **Supported** | n/a |
| H5 | Raw vs mix-adjusted change, 2017 → latest 12 months | Raw **+53.7%**; adjusted **+57.4%**; difference **−3.7 pp** | Raw 52.9 to 54.4; adjusted 56.8 to 58.0 | — | ≥ 2 pp and CIs not overlapping | **Material composition effect** | — |

"< 0.001" is shown instead of the computed value: with about 50,000 observations the p-values underflow to zero, so the effect sizes carry the interpretation (§1).

### Robustness (H1–H3)

| ID | M1 recent (primary) | M1 full period | M1 excluding retained duplicates | M2 binned (implied slope) |
|---|---:|---:|---:|---:|
| H1 storey, +10 floors | 7.77% | 8.02% | 7.76% | 7.64% |
| H2 lease, +10 years | 10.63% | 10.51% | 10.63% | 10.80% |
| H3 area, +10 sqm | 9.27% | 8.53% | 9.27% | n/a (area is not binned in M2) |

All specifications agree in direction and in clearing the 2% threshold.

### Assumption checks (M1, recent window)

| Check | Result | Assessment |
|---|---|---|
| Fit | R² = 0.916 (full period 0.919) | The observed characteristics explain most variation in log price *within this specification*. This is an in-sample fit, not predictive accuracy (that is Phase 3). |
| Residual shape | Skew 0.27, excess kurtosis 1.02 | Mildly heavy-tailed. Inference relies on large-sample cluster-robust errors, which do not need normal residuals. |
| Residual spread by fitted decile | SD 0.073–0.100 | Moderate heteroskedasticity, handled by robust (clustered) standard errors |
| VIF | Floor area 24.3, storey 1.27, lease 2.98 | Floor area is highly collinear with flat type, which is expected since type largely determines size. The H3 CI is still narrow (±0.4 pp), so precision is adequate. The coefficient is a *within-type* effect, as intended. |
| Linearity | M2 bins (Figures 07 and 08) | Storey is close to linear. Lease is **not** linear (see E2), although the M2 implied slope matches M1. |

### H1 — Storey: Supported (robust)
- **Plain English:** comparing flats sold in the same month, town, flat type and model, with the same floor area and remaining lease, a flat about 10 floors higher sold for roughly **8% more** on average. That is about SGD 49,000 at the recent median of SGD 628,000.
- **Raw versus adjusted:** raw medians rise from about SGD 570k (floors 1–3) to over SGD 1.4m (floors 43+). That is mostly because very tall blocks are concentrated in central, expensive towns. After adjustment, the top bands are about 25–33% above the lowest band (Figure 07). The three highest bands (43–51 floors) have only 18, 7 and 3 sales, so their individual estimates are imprecise; the wide CI in Figure 07 shows this. Raw storey comparisons therefore greatly overstate the floor-level premium.
- **Limitations:** the storey band is a three-floor range. View, facing and block design are unobserved, and high floors in the same town may sit in newer or better-located blocks.

### H2 — Remaining lease: Supported (robust), with a non-linear shape
- **Plain English:** for otherwise comparable flats, 10 more years of remaining lease was associated with about **11% higher** prices on average.
- **Caution:** remaining lease is tied to building age, condition, design era and upgrading history, and flat model captures this only partly. The estimate is a combined "newer flat with a longer lease" association. It should **not** be read as the value of lease length alone.
- **Shape:** see E2.

### H3 — Floor area within flat type: Supported (robust)
- **Plain English:** among flats of the same type, an extra 10 sqm was associated with about **9% higher** prices (full period 8.5%).
- **Limitations:** floor area includes recesses and roof terraces (publisher's note), and the high VIF means the effect is identified from size variation *within* types, which is narrower than across types.

### H4 — Town differences for 4-ROOM flats: Supported
- 26 towns were tested, all with at least 30 4-ROOM sales (none excluded), n = 22,175. Kruskal–Wallis H = 9,389 and **ε² = 0.42**, a large effect: town accounts for about 42% of the rank variation in 4-ROOM prices.
- Median 4-ROOM prices range from **SGD 537,500 (Jurong West) to SGD 1,200,000 (Central Area)**, a ratio of 2.23. Central Area has only 149 sales and a wide spread (25th–75th percentile roughly SGD 0.8m–1.4m).
- **After controls (M1, all flat types):** town effects still span about **61 percentage points**. Choa Chu Kang is 25% below and Bukit Timah 35% above Ang Mo Kio (the reference town), holding month, type, model, area, storey and lease fixed.
- **Limitations:** observations within a building are not independent, so the KW p-value is optimistic (the effect size is the main evidence). Town is a broad label that bundles location, amenities and building age.

### H5 — Composition effect: Material composition effect
- **Raw median:** SGD 410,000 in 2017 (n = 20,362) and SGD 630,000 in 2025-10 to 2026-09 (n = 24,658), a change of **+53.7%** (bootstrap 95% CI 52.9–54.4%).
- **Mix-adjusted (hedonic index):** **+57.4%** (delta-method 95% CI 56.8–58.0%).
- The raw median **understates** the price change for comparable flats by **3.7 percentage points**, and the CIs do not overlap.
- **Likely mechanism (interpretation, not a separate test):** the flats changing hands have aged. The median remaining lease of sold flats fell from 74.7 years (2017) to 71.1 years (2026, part-year), and H2 shows shorter leases go with lower prices. A rising share of sales on higher floors (18.6% to 21.3% with storey midpoint ≥ 13) works the other way, but the net effect is negative.
- **Limitation:** the index assumes the characteristic premiums are constant over 2017–2026. Unobserved changes in renovation quality are not adjusted for.

### Exploratory observations (not confirmatory)
- **E1, flat model** (`flat_model_effects_adjusted_recent.csv`, versus the 2-room reference): after controls, most mainstream models fall within about ±10% of each other. Larger adjusted premiums appear for DBSS (+18%), Type S1/S2 (+23%), Premium Apartment Loft (+16%) and Terrace (+79%, n = 23).
  - Small groups (Terrace n = 23, Improved-Maisonette n = 4, Premium Maisonette n = 8) have wide CIs and should not be relied on.
  - The `Multi Generation` coefficient is not separately identified (see deviations above).
- **E2, lease shape** (`lease_band_effects_adjusted_recent.csv`, Figure 08): relative to 35–39 years remaining, adjusted prices are 25.5% higher at 45–49 years, 55% at 55–59, 72% at 70–74, 101% at 80–84 and 113% at 95–99.
  - The reference band (35–39 years) holds only 59 sales, so the *level* of every percentage carries that band's uncertainty. The *shape* of the curve is better determined than any single value. The association is steepest at short remaining leases (below about 60 years), flatter between 60 and 80, and steps up again above 80.
  - The step above 80 years may reflect newer designs and building quality rather than lease as such.
  - This suggests the linear H2 summary averages over a curved relationship. Phase 3 models should allow non-linearity.
- **E3, thin data:** 18 of the 129 town × flat-type cells in the recent window have fewer than 30 sales. Examples include MULTI-GENERATION in Bishan (1), 2 ROOM in Serangoon (1), and 1 ROOM overall (18 sales). Segment statistics for these cells are labelled *low sample* in all tables.
