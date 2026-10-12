# Model Card — Indicative HDB Resale Price Estimator

> Sections 1–6 were written and committed **before any model was trained** (Phase 3 plan). Sections 7 onward contain executed results only.

## 1. Intended use

**Prediction scenario:** estimate the resale price of a flat whose transaction is registered in month *t*, using only:

- the flat's observable attributes: town, flat type, flat model, floor area, storey range, remaining lease, lease commencement year, and street (location); and
- a model trained on transactions registered **before** *t*.

The intended users are people comparing resale flats who want a **data-driven indicative price** with a visible typical error, and analysts studying where prices are hard to explain.

**Not intended for:**
- official valuation, mortgage or loan decisions, or the HDB valuation process;
- forecasting future prices beyond the data's coverage;
- estimating asking prices or setting negotiation targets;
- flats or segments with too little data, which are flagged rather than estimated with false precision.

The output is an **indicative estimate of the typical registered price** for comparable flats. It is *not* the market value of a specific unit, which depends on unobserved condition, renovation, view and facing.

## 2. Data

- **Source:** HDB resale transactions from January 2017 onwards (data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`). See DATA_QUALITY.md.
- **Rows:** analysis-ready rows only. Quarantined rows and the partial month are excluded.
- **Target:** `resale_price_sgd`. Models are fitted on `log(price)`, because prices are right-skewed (skewness about 0.9) and errors scale with price. Predictions are back-transformed with `exp()`, which estimates the conditional *median* price. That matches MAE as the primary metric.

## 3. Chronological split (pre-specified)

Splits are defined relative to the snapshot's **last full month L** (2026-09 for the 2026-10-12 snapshot).

| Split | Months | Purpose |
|---|---|---|
| Train | 2017-01 to L − 24 (2024-09) | Fit candidate models |
| Validation | L − 23 to L − 12 (2024-10 to 2025-09), 12 months | **All** model, feature-set and hyperparameter selection |
| Test | L − 11 to L (2025-10 to 2026-09), 12 months | **One** final evaluation of pre-selected configurations. Never used for choices. |

**Why 12-month validation and test blocks:** a full year covers seasonality, gives roughly 25,000 test rows (enough for segment analysis), and mirrors "how well does a model trained up to a date perform over the following year".

**Two evaluation modes on the test year:**
1. **Static:** the selected configuration is refit on train + validation (through L − 12) and predicts every test month. This shows how accuracy decays with horizon (1–12 months ahead).
2. **Monthly refit (rolling origin):** for each test month *m*, the selected configuration is refit on all data before *m* and predicts month *m* only. This shows deployment-realistic accuracy if the model is retrained monthly.

Neither mode makes any selection decision on test data.

**Unseen categories** in validation or test (for example, a street not in training) are mapped to "unknown" by the encoders. The counts of affected rows are reported.

## 4. Candidate models (pre-specified)

| ID | Model | Features | Rationale |
|---|---|---|---|
| B0 | Global training median | none | Required naive baseline |
| B1 | Segment median: town × flat type, falling back to flat type, then global | town, flat_type | A strong, explainable baseline. This is what a person would do by hand. |
| L-A | Ridge regression on log price | Core set A (below) | Interpretable linear model |
| L-B | Ridge regression on log price | Set A + street target encoding | Tests whether finer location helps a linear model |
| G-A | HistGradientBoosting on log price | Set A | Non-linear, captures interactions (for example, storey premium varying by town) |
| G-B | HistGradientBoosting on log price | Set A + street target encoding | |

**Core feature set A:**
- `town`, `flat_type`, `flat_model` (categorical);
- `floor_area_sqm_num`, `storey_mid`, `remaining_lease_years`, `lease_commence_year` (numeric);
- `months_since_start`, a time index (months since 2017-01).

For Ridge, remaining lease and the time index enter as **spline bases** so non-linear shapes can be captured.

**Street target encoding:** the mean log price per street, fitted with scikit-learn's `TargetEncoder` inside the training pipeline, using internal cross-fitting so a row never sees its own price.

**Hyperparameter grids (small, validation-selected):**
- Ridge: α ∈ {0.1, 1, 10}.
- HGB: `max_leaf_nodes` ∈ {31, 127} × `min_samples_leaf` ∈ {20, 100}, learning rate 0.1, up to 1,000 iterations with early stopping on an internal 10% random split of the training data. Seed 42.

**Addendum (added while implementing, before any model was trained; DEC-020):**
- The Ridge grid also includes `time_extrapolation` ∈ {`constant`, `linear`}. This decides how the time spline behaves *beyond* the training months: hold the last price level flat, or continue the final trend.
  - It matters because validation and test lie entirely outside the training period.
  - It is selected on validation like the other hyperparameters.
- Ridge one-hot encoding groups categories with fewer than 5 training rows into an "infrequent" level (`min_frequency=5`), so ultra-rare categories cannot get noisy individual coefficients.
- The grid therefore has 12 Ridge and 8 HGB configurations, 20 in total.

## 5. Leakage controls (pre-specified)

- **Forbidden as features:**
  - `resale_price` and anything derived from it: `resale_price_sgd`, `log_price`, `price_per_sqm_sgd`.
  - `duplicate_group_size`, which is computed over all fields, including price.
  - `source_row_number`. The source file is ordered by month, town and flat type, and *largely by ascending price* within those groups. Phase 1 found most groups in price order, although some years, for example 2020 and 2025–26, contain many out-of-order rows. The row number can therefore encode price rank.
  - `block`, which is high-cardinality and close to identifying a transaction. The building-level price signal is deliberately left out to keep the model a location-level estimator.
  - Data-quality flags and derived consistency fields.
- **No test-time information:** a code-level assertion rejects forbidden columns, and a unit test checks it.
- **Training-only fitting:** encoders, splines, scalers and the target encoder are fitted inside scikit-learn `Pipeline`s, only on the rows passed to `fit`.
- **No test-based selection:** all selection uses validation metrics only.
- **Feature availability:**
  - All features are known before the transaction: flat attributes, lease remaining at sale, and month of sale.
  - `remaining_lease` at the sale date is computable in advance from the lease start, so it is not leakage.
  - The time index is known at estimation time. It cannot be used *outside* the data's coverage, and the model card forbids that use.

**Disclosure:** Phase 2's exploratory analysis looked at all months, including the later test year. It informed the *candidate* feature design, for example lease splines because the lease relationship looked non-linear. Whether splines are actually used is decided on validation data. Hypothesis test results were not used to choose models.

## 6. Metrics and selection rule (pre-specified)

- **Primary metric:** MAE in SGD. It is the typical dollar error and robust to a few extreme prices.
- **Also reported:** RMSE (SGD), R², median absolute error (SGD), and median absolute percentage error (MdAPE, supplementary, because buyers think in % terms).
- **Selection:** the configuration with the lowest **validation MAE** across L-A, L-B, G-A and G-B. If the best two are within 1% MAE of each other, prefer the simpler one (linear before tree, feature set A before B).
- **Baselines:** reported on validation and test, and every candidate must beat B1 to be considered useful.
- **Segment analysis (test):** MAE and MdAPE by town, flat type, flat model, storey band, actual-price quintile, and test month (horizon). Segments with fewer than 30 test rows are labelled *less reliable*.
- **Prediction intervals (optional):**
  - Split-conformal 80% intervals from validation log-residuals of the train-only model (empirical 10th/90th percentiles), applied to the static test predictions.
  - Empirical coverage on test is reported, overall and by horizon.
  - If coverage falls materially below 80%, intervals are labelled unreliable and are not published in the BI layer.

## 7. Results (executed 2026-10-12, snapshot `20261012T010041Z`)

Produced by `python -m src.modelling.run_modelling` (254 s). Sources: `outputs/model_metrics/*.csv` and `model_results.json`.

### 7.1 Split as executed

| Split | Months | Rows |
|---|---|---:|
| Train | 2017-01 to 2024-09 (93 months) | 190,655 |
| Validation | 2024-10 to 2025-09 (12) | 26,244 |
| Test | 2025-10 to 2026-09 (12) | 24,658 |

**Category coverage:**
- Every town, flat type and flat model in validation and test also appears in training.
- **Streets:** 538 validation rows (6 streets, for example NORTHSHORE DR and YISHUN ST 42/44) were on streets absent from training. In the test year, 139 rows were on streets absent from train + validation. These are new or newly resold areas.

### 7.2 Validation (selection)

| Family | Best configuration | Validation MAE | MdAPE | R² |
|---|---|---:|---:|---:|
| B0 global median | — | 202,690 | 26.7% | −0.77 |
| B1 town × type median, all history | — | 169,822 | 24.5% | −0.02 |
| B2 town × type median, last 12 months | — | 86,989 | 9.5% | 0.58 |
| L-A Ridge | α = 10, linear time extrapolation | 45,149 | 5.7% | 0.907 |
| L-B Ridge + street | α = 10, linear | 43,078 | 5.3% | 0.912 |
| G-A Gradient boosting | 31 leaves, min leaf 20 | 30,904 | 3.8% | 0.953 |
| **G-B Gradient boosting + street** | **31 leaves, min leaf 20** | **28,958** | **3.7%** | **0.961** |

- **Selected: G-B (31 leaves, min leaf 20).** It had the lowest validation MAE. The runner-up within 1% (G-B, 127 leaves: 28,988) is in the same complexity class, so the lower MAE won. G-A is 6.7% worse, outside the tie band.
- **Ridge time extrapolation:** `linear` won only at α = 10. At α = 0.1 and 1, `constant` was better by 4,000–7,500 SGD MAE. Linear extrapolation is therefore unstable (consistent with DEC-020), and the Ridge results should be read with that caveat.
- **Over-fitting check (training MAE versus validation MAE):** G-B 18,148 vs 28,958; Ridge L-B 36,547 vs 43,078. Part of each gap is genuine market drift after the training period: validation bias is −2.8%, meaning prices kept rising beyond what the model saw.
- **Early stopping never triggered:** every gradient-boosting configuration but two reached the 1,000-iteration cap (`n_iter` 862 and 960 for the two 127-leaf runs). A higher cap might help slightly. Any change must be selected on validation in a future iteration; it was not tuned here.

### 7.3 Test-year results (one-time evaluation)

| Model | Mode | MAE (SGD) | RMSE (SGD) | R² | MedAE (SGD) | MdAPE | Median bias |
|---|---|---:|---:|---:|---:|---:|---:|
| B0 global median | static | 206,703 | 275,499 | −0.64 | 150,000 | 25.9% | −22.2% |
| B1 town × type, all history | static | 160,130 | 200,347 | 0.14 | 132,000 | 21.4% | −21.3% |
| B2 town × type, last 12 months | static | 84,509 | 128,658 | 0.64 | 54,056 | 8.8% | −0.1% |
| L-A Ridge | static | 48,636 | 68,109 | 0.900 | 35,525 | 5.9% | −1.7% |
| L-B Ridge + street | static | 46,280 | 65,265 | 0.908 | 33,621 | 5.5% | −1.1% |
| G-A Gradient boosting | static | 30,438 | 43,487 | 0.959 | 21,975 | 3.5% | +0.8% |
| **G-B (selected)** | **static** | **27,578** | **39,437** | **0.966** | **20,036** | **3.2%** | **+0.8%** |
| **G-B (selected)** | **monthly refit** | **25,387** | **36,040** | **0.972** | **18,554** | **3.0%** | **+0.0%** |
| B2 | monthly refit | 84,093 | 127,199 | 0.65 | 54,294 | 8.8% | +0.4% |

- The selected model's MAE is **67% lower than the realistic baseline B2** (27,578 against 84,509). Test results are in line with validation (28,958), so the selection does not look over-fitted to the validation year.
- In plain terms, for a typical test sale the static estimate was within **3.2%** of the registered price.
  - 80% of estimates fell between **−5.3% and +7.6%** of actual.
  - 7.4% of estimates missed by more than 10%, and 0.5% by more than 20%.

### 7.4 Accuracy over time (horizon)

| Test month | Months after training | MAE static | MAE monthly refit | Static median bias |
|---|---:|---:|---:|---:|
| 2025-10 | 1 | 23,978 | 23,978 | −0.3% |
| 2026-01 | 4 | 24,186 | 23,656 | +0.3% |
| 2026-04 | 7 | 26,276 | 24,624 | +0.7% |
| 2026-07 | 10 | 28,669 | 25,469 | +1.3% |
| 2026-09 | 12 | 33,614 | 27,849 | +1.3% |

The model trained once loses accuracy steadily: MAE is about 40% higher by month 12, and it drifts towards over-estimation. Retraining monthly keeps MAE between 23,700 and 27,800 with near-zero bias. **Recommendation: any deployed use should retrain at least monthly.**

### 7.5 Where the model is less reliable (static test, selected model)

| Segment | Finding |
|---|---|
| Flat type | Main types: 3.0–3.5% MdAPE. **1 ROOM (n = 9, 5.2%)** and **MULTI-GENERATION (n = 6, 9.4%, under-estimated)** are less reliable because of tiny samples. |
| Flat model | Rare models are poor: Terrace (n = 10, 9.6%), Adjoined flat (n = 43, 6.9%), Type S2 (n = 17, 5.6%), Improved-Maisonette (n = 2). Most common models: 2.9–3.7% (Model A, Improved, New Generation, Premium Apartment), but Standard reaches 4.9% (n = 584). |
| Town | Best: Bukit Batok, Pasir Ris and Tampines (about 2.7%). Worst: **Marine Parade (5.5%, n = 131)**, Queenstown and Toa Payoh (4.4%). These are mature, central towns with more heterogeneous stock. |
| Price quintile | MAE rises with price, reaching 46,279 in the top quintile. % error is lowest in the middle quintiles (2.8–2.9%). The model **over-estimates cheap flats** (Q1 bias +2.7%) and **under-estimates expensive ones** (Q5 −1.8%), regression towards the middle. |
| Storey | 2.7–4.0% for bands with at least 30 test sales. The top bands (43+ floors, n ≤ 9) are less reliable. |
| New streets | 139 test rows on streets unseen in training: MAE 49,293 and MdAPE 4.2%, against 27,455 and 3.2% for known streets |

### 7.6 What the model relies on (permutation importance, 5,000-row test sample)

| Feature | MAE increase when shuffled (SGD) |
|---|---:|
| Floor area | 83,750 |
| Town | 73,457 |
| Lease commencement year | 45,188 |
| Flat type | 30,723 |
| Street (target-encoded) | 25,921 |
| Storey | 15,094 |
| Flat model | 12,863 |
| Remaining lease | 5,486 |
| Time index | 0 |

**Interpretation:**
- Lease commencement year and remaining lease carry almost the same information, so they share importance. Their combined role is substantial. Remaining lease looks small only because lease commencement year already carries it.
- The **time index has zero importance in static test mode** by construction. Every test month lies beyond the training range, and a tree treats them all as the latest training month. The model therefore predicts at the price level of its last training month, which explains the horizon decay in §7.4.
- Importance describes reliance, not causal effect.

### 7.7 Prediction intervals: **not published**

- **Calibration:** split-conformal 80% intervals were calibrated on validation residuals of the train-only model, giving multipliers of 0.970 to 1.092 × the estimate. The interval is asymmetric because the market rose during validation.
- **Test coverage:** **64.9% static and 70.9% monthly refit**, against the nominal 80%. Static coverage falls from 74% at month 1 to 58% at month 12.
- **Why:** the residual distribution shifted between the validation year, when prices were still rising, and the test year, when they were flat. The intervals were too narrow and centred in the wrong place. This violates the conformal method's exchangeability assumption under drift.
- **Decision (per pre-specified rule, DEC-023):** coverage is materially below 80%, so the intervals are labelled **unreliable and are not shown** in the BI layer. The BI report instead shows the empirical error distribution and segment MdAPE.

### 7.8 Leakage checks performed

- **Forbidden features:** unit tests assert that target-derived, row-order, duplicate and identifier columns are rejected (`test_forbidden_columns_rejected`, `test_feature_sets_contain_no_forbidden_or_target`).
- **Training-only target encoding:** inflating validation prices tenfold leaves predictions unchanged (`test_target_encoder_fitted_only_on_training_rows`).
- **Chronology:** the split is strictly chronological and disjoint (`test_split_is_chronological_and_disjoint`).
- **No test-set choices:** all selection used validation only. The single post-hoc change (adding baseline B2) cannot affect selection (DEC-021).

## 8. Limitations

1. **Single test year** (2025-10 to 2026-09), which was a flat market. Performance in a fast-rising or falling market will be worse in static mode, as validation's −2.8% bias shows.
2. **No unit-level information:** condition, renovation, view, facing, exact floor and block-level location (excluded by design) all contribute to residual error.
3. **Rare segments:** fewer than 30 test sales means less reliable estimates. Examples include 1 ROOM, MULTI-GENERATION, Terrace and the highest storey bands.
4. **New areas:** streets unseen in training get a generic location estimate, with error about 50% higher.
5. **Time:** the model cannot extrapolate market movements. It holds the last level it saw.
6. **Intervals:** no reliable uncertainty interval is available (§7.7).
7. **Hyperparameters:** the gradient-boosting iteration cap was reached, so some accuracy may be left on the table.

## 9. Prohibited interpretations

- ✗ "The model says this flat is worth SGD X." It estimates the typical registered price of *comparable* flats.
- ✗ Using estimates as a valuation, a loan basis or a negotiation floor or ceiling.
- ✗ Reading feature importance as "what causes prices".
- ✗ Applying the model to months beyond the data's coverage, or to flats with attributes outside the training range.
- ✗ Trusting estimates for segments labelled less reliable.
