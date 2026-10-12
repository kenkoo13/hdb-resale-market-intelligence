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

*Business metrics, statistical measures, model metrics and DAX measures are added in Phases 2–4.*
