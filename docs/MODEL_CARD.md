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

## 7. Results

*Not yet run.*
