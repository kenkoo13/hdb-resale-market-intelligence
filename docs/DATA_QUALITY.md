# Data Quality

How the source data is checked and cleaned, and what the checks found.
The figures below come from the **2026-10-12 snapshot** (`20261012T010041Z`, SHA-256 `32b767d6…7fecdf`) and were produced by `python -m src.pipeline`.
Each run regenerates the full machine-produced report at [`outputs/data_quality/dq_report.md`](../outputs/data_quality/dq_report.md), with a JSON version alongside. When a later snapshot gives different numbers, that report is authoritative and this page should be updated.

## 1. Snapshot summary

| Measure | Value |
|---|---:|
| Source rows (raw CSV) | 242,454 |
| Rows quarantined (exception report) | 147 |
| Clean rows | 242,307 |
| Rows in the partial month (2026-10, still accumulating) | 750 |
| **Analysis-ready rows (clean, full months only)** | **241,557** |
| Months covered | 2017-01 to 2026-10 (118 months, none missing) |
| Rows per full month | min 363 (2020-05), max 3,036 |
| Source "last updated" timestamp | 2026-10-12T02:10:19+08:00 |

**Blocking gates:** all passed. The header matched the 11-column contract, the declared types were unchanged, the row count was non-zero, and the pandas row count matched the manifest. This was the first snapshot, so there was no earlier row count to compare against.

## 2. Field-level checks (raw text)

| Field | Blank | Parse failures | Distinct | Notes |
|---|---:|---:|---:|---|
| month | 0 | 0 | 118 | All match `YYYY-MM` |
| town | 0 | n/a | 26 | Matches the reference set; no new towns |
| flat_type | 0 | n/a | 7 | Sparse: `1 ROOM` (89), `MULTI-GENERATION` (91) |
| block | 0 | n/a | 2,788 | Alphanumeric, for example `337A`. Kept as text. |
| street_name | 0 | n/a | 580 | Abbreviated (`AVE`, `ST`, `RD`) exactly as in the source |
| storey_range | 0 | 0 | 17 | Three-storey bands from `01 TO 03` to `49 TO 51` |
| floor_area_sqm | 0 | 0 | 352 | Declared as *Text* by the publisher. All values numeric, 31–366.7 sqm. |
| flat_model | 0 | n/a | 21 | No case variants found (R03 changed 0 rows) |
| lease_commence_date | 0 | 0 | 58 | Declared as *Text*. All values are 4-digit years, 1966–2023. |
| remaining_lease | 0 | 0 | 703 | Three formats, all parsed (see §5) |
| resale_price | 0 | 0 | 4,802 | SGD 140,000–1,728,000 |

No field had leading or trailing whitespace, and no text needed case normalisation. Rules R01 and R02 changed 0 rows. They stay in place so a future refresh is protected.

## 3. Cleaning rules

Codes beginning `Q` quarantine the row, `F` flags it, and `R` normalise it. Affected counts are for the 2026-10-12 snapshot.

| Code | Rule | Action | Rows | Rationale |
|---|---|---|---:|---|
| R01 | Trim and collapse whitespace in all text fields | Normalise | 0 | Prevents `"BEDOK "` and `"BEDOK"` being treated as different categories |
| R02 | Upper-case town, flat_type, street_name, storey_range | Normalise | 0 | The source uses upper case for these code lists |
| R03 | Unify flat_model case variants to the most frequent spelling | Normalise | 0 | Defensive |
| Q01 | Blank core field (month, town, flat_type, storey_range, floor_area_sqm, resale_price) | Quarantine | 0 | Row cannot be used for core analysis (DEC-010) |
| Q02 | Month not `YYYY-MM` | Quarantine | 0 | |
| Q03 | Month before 2017-01 or after the retrieval month | Quarantine | 0 | Outside dataset coverage |
| Q04 | Price non-numeric or ≤ 0 | Quarantine | 0 | |
| Q05 | Floor area non-numeric or ≤ 0 | Quarantine | 0 | |
| Q06 | Storey range not `NN TO NN`, or lower > upper | Quarantine | 0 | |
| **Q07** | **Suspected 2017 duplicate-publication artefact** | **Quarantine** | **147** | §4 and DEC-013 |
| F | `flag_invalid_lease_commence` (not a year, or after the transaction year) | Null field, keep row | 0 | |
| F | `flag_invalid_remaining_lease` | Null field, keep row | 0 | |
| F | `flag_missing_block` / `street_name` / `flat_model` | Null field, keep row | 0 | |
| F | `flag_lease_inconsistent` (source vs derived > 1.5 years) | Keep, flag | 1 | DEC-012 |
| F | `flag_implausible_floor_area` (outside 20–400 sqm) | Keep, flag | 0 | DEC-011 |
| F | `flag_implausible_price` (outside SGD 50k–3M) | Keep, flag | 0 | DEC-011 |
| F | `flag_new_category` (town or flat type not in the reference set) | Keep, flag | 0 | Surfaces a new town instead of dropping it |
| F | `is_partial_month` (month ≥ retrieval month, SGT) | Keep, flag; excluded from trends and model evaluation | 750 | DEC-008 |
| F | `duplicate_group_size > 1` (retained exact duplicates) | Keep, annotate | 341 rows in 170 groups | DEC-013 |

Rows are never deleted silently. Every removed row is in `data/processed/quarantine.csv` with its original text, source row number and reason codes.

## 4. Duplicate investigation

The source has no transaction ID. A *duplicate* here means a row identical to another on all 11 source fields.

| Finding (2026-10-12 snapshot) | Value |
|---|---|
| Rows in exact-duplicate groups | 635 (317 groups; 316 pairs and 1 triple) |
| Excess rows if fully de-duplicated | 318 (0.13%) |
| Duplicate rate, 2017 | **1.68%** (344 rows) |
| Duplicate rate, 2018–2026 | 0.08%–0.21% a year |
| 2017 duplicate rows priced at exactly 468,000 or 470,000 | **294 of 344** |
| Duplicate rows at those prices in any other year | **0** |
| Position of the second copy (2017) | Usually *not* adjacent: median gap 9.5 rows, and only 11.6% adjacent. It typically appears out of the run's price order. |
| Position of the second copy (2018+) | 78.4% on the adjacent row |
| 2017 rows at 468k/470k: with artefact copies / without | 379 / 232. 2018 has 220. |

**Interpretation:** The pattern in 2017 at those two prices is very unlikely to reflect real transactions, so it is treated as a suspected publication artefact. Its 147 excess copies are quarantined and the first copy of each pair is kept. The other duplicates match genuine near-identical sales: the same block, storey band, model and month at a round price. Of the retained duplicates, 94.7% have prices that are multiples of 1,000, compared with 92.1% of all rows. They are kept (DEC-013).

**Sensitivity:** Applying the rule leaves the 2017 median price (SGD 410,000) and the overall median (SGD 505,000) unchanged. Five 2017 monthly medians change by at most SGD 5,000.

## 5. Remaining lease

| Format | Rows | Example |
|---|---:|---|
| `N years N months` | 202,948 | `61 years 04 months` |
| `N years` | 19,889 | `63 years` (0 months) |
| `N years N month` | 19,617 | `62 years 01 month` |

All three formats appear in every year from 2017 to 2026 in similar proportions, so the format is not a time artefact.

**Consistency with lease start year:** the source value minus the derived value (99 years from 1 January of `lease_commence_date`) has a median of 0.50 years and a 1st–99th percentile range of 0.00–1.00. That is exactly the bias expected from not knowing the lease start month. One row exceeds the 1.5-year tolerance (see DEC-012). The source remaining lease is consistent with the publisher's own lease data, so it is the preferred lease variable.

## 6. Numeric ranges (clean rows)

| Field | Min | 1st percentile | Median | 99th percentile | Max |
|---|---:|---:|---:|---:|---:|
| Resale price (SGD) | 140,000 | 235,000 | 505,000 | 1,109,933 | 1,728,000 |
| Floor area (sqm) | 31 | 47 | 93 | 151 | 366.7 |
| Price per sqm (SGD) | 2,090 | 3,106 | 5,328 | 11,376 | 16,716 |
| Lease commence year | 1966 | 1969 | 1997 | 2020 | 2023 |
| Remaining lease (years) | 39.3 | 45.8 | 73.75 | 95.25 | 97.75 |
| Storey midpoint | 2 | 2 | 8 | 29 | 50 |

## 7. Transaction volume observations (data-quality relevance only)

- **2020-04 (424 rows) and 2020-05 (363 rows)** are the lowest full months, against roughly 1,000–3,000 in other months. They are real low-volume months, not missing data. *Context, not derived from this dataset:* they coincide with Singapore's COVID-19 "circuit breaker" restrictions (April–June 2020). Statistics for these months rest on smaller samples.
- **2026-10** is partial (750 rows by 12 October) and is flagged.

## 8. Known limitations

1. **No transaction identifier.** Duplicate handling relies on evidence, not a key (DEC-013 is provisional).
2. **Registration month, not agreement date.** Prices reflect deals agreed some weeks earlier.
3. **Floor area includes extensions** (recess areas, upgrading additions, roof terraces), according to the publisher's note. Price per sqm therefore mixes different kinds of space.
4. **Storey is a three-floor band.** The exact floor is unknown.
5. **Location precision stops at the block or street.** There are no coordinates, by design (DEC-001).
6. **Single-snapshot evidence.** Whether earlier months receive late registrations cannot be assessed until several snapshots exist (DEC-008).
7. **The source excludes non-market resales** (between relatives, part shares), according to the publisher's note.
