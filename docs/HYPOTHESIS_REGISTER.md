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

## 3. Results

*Not yet run. This section is filled in from executed output only.*
