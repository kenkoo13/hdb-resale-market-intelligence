# Data Dictionary

## 1. Source fields (`data/raw/<snapshot>/resale_raw.csv`)

Source: HDB, data.gov.sg dataset `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`. Every field is read as **text** (DEC-010). The "Declared type" column is the publisher's own metadata label.

| Field | Declared type | Meaning | Format / allowed values (observed 2026-10-12) | Missing-value handling |
|---|---|---|---|---|
| `month` | Month (YYYY-MM) | Month the resale was **registered** with HDB | `YYYY-MM`, 2017-01 to the current month | Blank or invalid → quarantine (Q01/Q02/Q03) |
| `town` | Text | HDB town | 26 upper-case values, for example `ANG MO KIO`, `KALLANG/WHAMPOA` | Blank → quarantine. New value → kept and flagged. |
| `flat_type` | Text | Room-count category | `1 ROOM`, `2 ROOM`, `3 ROOM`, `4 ROOM`, `5 ROOM`, `EXECUTIVE`, `MULTI-GENERATION` | Blank → quarantine. New value → kept and flagged. |
| `block` | Text | Block number | Alphanumeric, for example `406`, `337A` | Blank → null and flag |
| `street_name` | Text | Street name (abbreviated) | 580 values | Blank → null and flag |
| `storey_range` | Text | Three-storey band containing the unit | `NN TO NN`, from `01 TO 03` to `49 TO 51` | Blank or invalid → quarantine |
| `floor_area_sqm` | Text | Approximate floor area in square metres, including recess, upgrading additions and roof terrace | Unsigned decimal; observed 31–366.7 | Blank or invalid → quarantine. `0` is parsed as zero and then quarantined as ≤ 0. |
| `flat_model` | Text | HDB design model | 21 values, for example `Model A`, `Improved`, `DBSS`, `Premium Apartment` | Blank → null and flag |
| `lease_commence_date` | Text | **Year** the 99-year lease started | 4-digit year, 1966–2023 | Invalid or after the transaction year → null and flag |
| `remaining_lease` | Text | Lease remaining at the time of sale, as recorded by HDB | `N years`, `N years N month`, `N years N months` | Unparseable → null and flag |
| `resale_price` | Numeric | Registered resale price, SGD | Unsigned decimal; observed 140,000–1,728,000 | Blank or invalid → quarantine |

## 2. Clean table (`data/processed/transactions_clean.parquet`)

**Grain:** one row per retained published resale record (the dataset's transaction grain). The 11 source columns are carried forward after normalisation (R01–R03). Derived columns are listed below. Formulas are in [METRIC_DICTIONARY.md](METRIC_DICTIONARY.md).

| Column | Type | Unit | Definition |
|---|---|---|---|
| `source_row_number` | int64 | — | 1-based data-row position in the raw CSV. Used for lineage back to the source row. |
| *11 source columns* | string | — | Normalised source text |
| `month_date` | datetime64 | date | First day of `month` |
| `year` | Int64 | year | Calendar year of `month_date` |
| `floor_area_sqm_num` | float64 | sqm | Parsed `floor_area_sqm` |
| `resale_price_sgd` | float64 | SGD | Parsed `resale_price` |
| `storey_lower`, `storey_upper` | Int64 | floor | Bounds of `storey_range` |
| `storey_mid` | float64 | floor | Midpoint of the band, an approximate floor |
| `lease_commence_year` | Int64 | year | Parsed `lease_commence_date`. Null if invalid or later than the transaction year. |
| `remaining_lease_months` | Int64 | months | Parsed `remaining_lease` |
| `remaining_lease_years` | float64 | years | `remaining_lease_months / 12` |
| `price_per_sqm_sgd` | float64 | SGD/sqm | `resale_price_sgd / floor_area_sqm_num` |
| `derived_remaining_lease_years` | float64 | years | Consistency check only (DEC-012) |
| `lease_discrepancy_years` | float64 | years | `remaining_lease_years − derived_remaining_lease_years` |
| `is_partial_month` | bool | — | Month ≥ retrieval month (SGT). Excluded from trends and modelling. |
| `duplicate_group_size` | int64 | rows | Number of retained rows identical on all 11 source fields (1 = unique) |
| `flag_invalid_lease_commence` | bool | — | See DATA_QUALITY §3 |
| `flag_invalid_remaining_lease` | bool | — | " |
| `flag_missing_block` / `_street_name` / `_flat_model` | bool | — | " |
| `flag_lease_inconsistent` | bool | — | " |
| `flag_implausible_floor_area` / `_price` | bool | — | " |
| `flag_new_category` | bool | — | " |

## 3. Exception report (`data/processed/quarantine.csv`)

The raw text of every quarantined row, unchanged, plus `source_row_number` and `quarantine_reasons`: a semicolon-separated list of the reason codes in DATA_QUALITY §3.

## 4. Run metadata

- `data/raw/<snapshot>/manifest.json`: snapshot ID, dataset ID, retrieval time (UTC and SGT), the publisher's metadata (last updated, declared coverage, declared columns and types), CSV header, row count, byte size, SHA-256.
- `data/processed/run_info.json`: the snapshot that was processed, counts, month coverage, partial months, processing time.

## 5. Analysis outputs (`outputs/tables/`, Phase 2)

Common columns in segment tables: `transactions`, `median_price`, `p25_price`, `p75_price`, `iqr_price`, `mean_price`, `median_price_per_sqm`, `median_floor_area_sqm`, `median_remaining_lease_years`, and `low_sample` (n < 30). Definitions are in METRIC_DICTIONARY §2.

| File | Grain | Population |
|---|---|---|
| `monthly_market.csv` | month | All clean rows; `is_partial_month` flags the incomplete month |
| `annual_by_flat_type.csv` | year × flat type | Analysis-ready |
| `mix_over_time.csv` | year | Analysis-ready; flat-type shares (`share_pct_*`), median area, median lease, % of sales on storey midpoint ≥ 13 |
| `price_distribution_summary.csv` | population | Full period and recent window; mean, median, skewness, p10/p90 |
| `recent_by_{flat_type,town,storey_range,flat_model,lease_band}.csv` | segment | Recent window |
| `recent_4room_by_town.csv` | town | Recent window, 4 ROOM |
| `recent_by_town_flat_type.csv` | town × flat type | Recent window, sorted with low-sample cells first |
| `recent_by_floor_area_band_flat_type.csv` | flat type × area band | Recent window |
| `price_index_monthly.csv` | month | `raw_median_index` and `mix_adjusted_index` (2017 = 100) |
| `hedonic_key_coefficients.csv` | model × term | Per-unit % effects for area, storey and lease |
| `{town,flat_model,storey_band,lease_band}_effects_adjusted_recent.csv` | level | % vs reference level, 95% CI |
| `hypothesis_results.csv`, `hypothesis_robustness.csv`, `h5_composition.csv` | hypothesis | See HYPOTHESIS_REGISTER §3 |
| `analysis_results.json` | run | Windows, row counts, results, diagnostics, snapshot id |

## 6. Model outputs (`outputs/model_metrics/`, Phase 3)

| File | Grain | Key columns |
|---|---|---|
| `validation_scores.csv` | configuration | family, config, n, mae, rmse, r2, medae, mdape_pct, bias_median_pct, fit_seconds, n_iter |
| `train_scores.csv` | configuration | In-sample metrics, used for the over-fitting check |
| `test_scores.csv` | model × mode | mode (`static` / `monthly refit`), family, config, metrics, selected |
| `test_errors_by_month.csv` | test month | horizon_months, MAE static / monthly refit / B2, bias, interval coverage |
| `test_segment_errors_{static,monthly_refit}.csv` | segment level | segment, level, metrics, median_actual, reliability |
| `permutation_importance.csv` | feature | mae_increase_sgd, std |
| `model_results.json` | run | Split, unseen categories, selected config, conformal quantiles and coverage |

`data/processed/model_test_predictions.parquet` (git-ignored) has one row per test transaction: attributes, `actual`, `predicted` (static), `predicted_rolling` / `predicted_monthly_refit`, all family predictions, interval bounds (**not for publication**, DEC-023), `price_quintile` and `horizon_months`.

## 7. Power BI import tables (`data/curated/`, Phase 4)

Built by `python -m src.reporting.build_bi_tables`. The star schema is defined in `sql/01_fact_and_dimensions.sql`.

| Table | Grain | Columns | Committed |
|---|---|---|---|
| `fact_transactions` | transaction | txn_id (= source_row_number), month (date), town, flat_type, flat_model, storey_range, storey_mid, floor_area_sqm, floor_area_band, remaining_lease_years, lease_band, lease_commence_year, resale_price (SGD), price_per_sqm (SGD) | No (about 30 MB; regenerated) |
| `dim_month` | month | month, year, quarter, month_label, is_partial_month, months_before_last_full, is_latest_12m, is_prior_12m, is_recent_24m (0/1) | Yes |
| `dim_town`, `dim_flat_model` | category | name | Yes |
| `dim_flat_type` | flat type | flat_type, flat_type_order (sort key) | Yes |
| `dim_storey_range` | band | storey_range, storey_order (sort key) | Yes |
| `price_index_monthly`, `hypothesis_results`, `*_effects_adjusted` | as in §5 | as in §5; hypothesis_results adds `plain_english` and an H5 row (estimate in percentage points) | Yes |
| `model_comparison` | model × mode | model_label (plain English), mode, family, config, n, mae, rmse, r2, medae, mdape_pct, bias_median_pct | Yes |
| `model_errors_by_month`, `model_segment_errors`, `model_feature_importance` | as in §6 | as in §6 | Yes |
| `indicative_profiles` | town × flat type × storey variant | profile attributes, estimate_month, estimated_price(_rounded), typical_error_pct / _sgd, reliability, segment_sales_latest_12m, segment_median_price_latest_12m, storey_band_sales_in_segment, estimate_vs_segment_median_pct | Yes |
| `refresh_info` | snapshot | snapshot_id, dataset_id, retrieved_at_local, source_last_updated_at, first_month, last_full_month, partial_month, clean_rows, quarantined_rows, attribution | Yes |
| `sql_check_town_flat_type_latest12` | town × flat type | SQL-computed n and median (cross-check evidence) | Yes |
| `dax_expected_values`, `dax_validation_results` | check | measure, filter_context, expected and actual values, pass | Yes |

