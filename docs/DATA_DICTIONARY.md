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

*Analytical and Power BI tables are added to this dictionary in Phases 2–4.*
