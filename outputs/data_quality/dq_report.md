# Data Quality Report — snapshot 20261012T010041Z

_Generated automatically by `src/validation/quality_report.py`. Do not edit by hand._

- Dataset: `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`; retrieved 2026-10-12T09:00:41.075283+08:00; source last updated 2026-10-12T02:10:19+08:00
- SHA-256: `32b767d68e9f22b2e48a95a942d233cb13b311f1d06633e456743020c47fecdf`
- Gates passed: **True**; blocking: none; warnings: none

## Counts

| Measure | Rows |
|---|---:|
| raw_rows | 242,454 |
| manifest_row_count | 242,454 |
| clean_rows | 242,307 |
| quarantined_rows | 147 |
| partial_month_rows | 750 |
| analysis_ready_rows_excl_partial_month | 241,557 |

## Coverage

- Months: 2017-01 to 2026-10 (118 months present)
- Missing months within range: none
- Partial (still-accumulating) months: ['2026-10']
- Rows per full month: min 363, max 3,036

## Field profile (raw text)

| Field | Blank | Blank % | Distinct | Parse failures (non-blank) | Untrimmed |
|---|---:|---:|---:|---:|---:|
| month | 0 | 0.0 | 118 | 0 | 0 |
| town | 0 | 0.0 | 26 | n/a | 0 |
| flat_type | 0 | 0.0 | 7 | n/a | 0 |
| block | 0 | 0.0 | 2,788 | n/a | 0 |
| street_name | 0 | 0.0 | 580 | n/a | 0 |
| storey_range | 0 | 0.0 | 17 | 0 | 0 |
| floor_area_sqm | 0 | 0.0 | 352 | 0 | 0 |
| flat_model | 0 | 0.0 | 21 | n/a | 0 |
| lease_commence_date | 0 | 0.0 | 58 | 0 | 0 |
| remaining_lease | 0 | 0.0 | 703 | 0 | 0 |
| resale_price | 0 | 0.0 | 4,802 | 0 | 0 |

## Rules and flags (affected rows)

| Rule / flag | Rows |
|---|---:|
| R01_whitespace_normalised:month | 0 |
| R01_whitespace_normalised:town | 0 |
| R01_whitespace_normalised:flat_type | 0 |
| R01_whitespace_normalised:block | 0 |
| R01_whitespace_normalised:street_name | 0 |
| R01_whitespace_normalised:storey_range | 0 |
| R01_whitespace_normalised:floor_area_sqm | 0 |
| R01_whitespace_normalised:flat_model | 0 |
| R01_whitespace_normalised:lease_commence_date | 0 |
| R01_whitespace_normalised:remaining_lease | 0 |
| R01_whitespace_normalised:resale_price | 0 |
| R02_uppercased:town | 0 |
| R02_uppercased:flat_type | 0 |
| R02_uppercased:street_name | 0 |
| R02_uppercased:storey_range | 0 |
| R03_flat_model_case_unified | 0 |
| Q01_missing_month | 0 |
| Q01_missing_town | 0 |
| Q01_missing_flat_type | 0 |
| Q01_missing_storey_range | 0 |
| Q01_missing_floor_area_sqm | 0 |
| Q01_missing_resale_price | 0 |
| Q02_invalid_month_format | 0 |
| Q03_month_outside_coverage | 0 |
| Q04_invalid_resale_price | 0 |
| Q05_invalid_floor_area | 0 |
| Q06_invalid_storey_range | 0 |
| Q07_suspected_duplicate_artefact | 147 |
| F_flag_invalid_lease_commence | 0 |
| F_flag_invalid_remaining_lease | 0 |
| F_flag_missing_block | 0 |
| F_flag_missing_street_name | 0 |
| F_flag_missing_flat_model | 0 |
| F_flag_lease_inconsistent | 1 |
| F_flag_implausible_floor_area | 0 |
| F_flag_implausible_price | 0 |
| F_flag_new_category | 0 |
| F_is_partial_month | 750 |
| F_rows_in_retained_duplicate_groups | 341 |
| F_retained_excess_duplicate_rows | 171 |

## Remaining lease

- Formats: {'N years N months': 202948, 'N years': 19889, 'N years N month': 19617}
- Discrepancy (source − derived, years): {'count': 242307.0, 'mean': 0.501, 'std': 0.293, 'min': -14.917, '1%': 0.0, '5%': 0.083, '50%': 0.5, '95%': 1.0, '99%': 1.0, 'max': 1.5}
- Rows with |discrepancy| above tolerance: 1

## Duplicates (identical on all 11 source fields)

- rows_in_duplicate_groups: 341
- duplicate_groups: 170
- excess_rows_if_deduplicated: 171
- group_size_distribution: {2: 169, 3: 1}
- by_flat_type: {'4 ROOM': 169, '3 ROOM': 84, '5 ROOM': 70, '2 ROOM': 12, 'EXECUTIVE': 4, '1 ROOM': 2}
- by_year: {'2017': 50, '2018': 18, '2019': 36, '2020': 40, '2021': 60, '2022': 36, '2023': 28, '2024': 30, '2025': 25, '2026': 18}
- share_price_multiple_of_1000: 0.9472
- share_price_multiple_of_1000_all_rows: 0.9207

## New categories vs reference sets

- {'town': [], 'flat_type': []}
