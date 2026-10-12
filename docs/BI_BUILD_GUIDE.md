# Power BI Build Guide

## 1. What exists and what has been verified

The report is a **Power BI Project (PBIP)** in text form. Python generates it from a single specification (`src/reporting/build_pbip.py`), and it targets **Power BI Desktop (free)**. Nothing requires Power BI Service, Pro or Premium.

| Item | Status (2026-10-12, Power BI Desktop 2.158, Sept 2026) | Evidence |
|---|---|---|
| `powerbi/HDB Resale Market.pbip` + `.SemanticModel` (TMDL) + `.Report` (PBIR) | Generated | `python -m src.reporting.build_pbip` |
| TMDL syntax and references | **Verified**: parsed by Power BI Desktop's own TMDL serializer (17 tables, 129 columns, 37 measures, 9 relationships) | `powerbi/tools/validate_tmdl.ps1` |
| Project opens in Power BI Desktop | **Verified**: the window titled "HDB Resale Market" loaded the model into the local engine | Engine inspection via TOM |
| Data refresh (Power Query → CSV import) | **Verified**: full refresh succeeded in 20 s; all 17 tables `Ready` | TOM `RequestRefresh(Full)` |
| Row counts vs source CSVs | **Verified**: 17 / 17 match | `powerbi/tools/query_model.ps1` |
| DAX measures vs Python/SQL expected values | **Verified**: 13 / 13 match (relative tolerance 1e-9) | Same script → `data/curated/dax_validation_results.csv` |
| All 37 measures evaluate without error | **Verified** | Same script |
| Every visual field exists in the model | **Verified**: automated check of all visual field references | `tests/test_bi.py::test_every_visual_field_exists_in_model` |
| Visuals render as intended (layout, formatting, readability) | **Requires visual check in Desktop** (see §8) | Not machine-verifiable here |
| A `.pbix` file | **Not produced by code**. Save it from Desktop (*File → Save as → .pbix*) if a single file is needed. | — |

## 2. How to open and refresh

1. Run the pipeline so the CSVs exist:
   `python -m src.pipeline` → `python -m src.analytics.run_analysis` → `python -m src.modelling.run_modelling` → `python -m src.reporting.build_bi_tables` → `python -m src.reporting.build_pbip`
2. Open `powerbi/HDB Resale Market.pbip` in Power BI Desktop.
3. **If the folder path differs on your machine:** go to *Transform data → Edit parameters → CuratedFolder* and set the absolute path to `data/curated/`, ending with `\`. Alternatively, re-run `build_pbip` on your machine, which writes your path automatically.
4. Click **Refresh**. The project stores no data (`.pbi/cache.abf` is git-ignored), so the first open always needs a refresh.
5. Optional validation: `powershell -ExecutionPolicy Bypass -File powerbi/tools/query_model.ps1`. All checks should print `passed`.

**Refresh behaviour:** Power BI imports CSVs. Refreshing Power BI does **not** download new HDB data. To update:
- rerun the Python commands in step 1;
- refresh Power BI;
- re-check page 1's coverage line, which shows the snapshot's retrieval time and last full month.

There is no scheduled or automatic refresh (DEC-003).

## 3. Data model (star schema)

Fact: `fact_transactions` (one row per registered resale, including the partial month, which is flagged in `dim_month`).

Dimensions:
- `dim_month` has the window flags `is_partial_month`, `is_latest_12m`, `is_prior_12m` and `is_recent_24m`.
- `dim_town`.
- `dim_flat_type` is sorted by `flat_type_order`, so it runs 1 ROOM, 2 ROOM … MULTI-GENERATION.
- `dim_storey_range` is sorted by `storey_order`.
- `dim_flat_model`.

Pre-computed result tables are imported as-is. They are **not** recomputed by DAX, and slicers do not change them unless a relationship below says otherwise:
- `price_index_monthly`, `hypothesis_results`;
- `storey_effects_adjusted`, `lease_effects_adjusted`, `town_effects_adjusted`;
- `model_comparison`, `model_errors_by_month`, `model_segment_errors`, `model_feature_importance`;
- `indicative_profiles`, `refresh_info`.

**Relationships** (all many-to-one, single direction from dimension to fact):

| From (many) | To (one) |
|---|---|
| `fact_transactions.month` | `dim_month.month` |
| `fact_transactions.town` | `dim_town.town` |
| `fact_transactions.flat_type` | `dim_flat_type.flat_type` |
| `fact_transactions.storey_range` | `dim_storey_range.storey_range` |
| `fact_transactions.flat_model` | `dim_flat_model.flat_model` |
| `price_index_monthly.month` | `dim_month.month` |
| `model_errors_by_month.month` | `dim_month.month` |
| `indicative_profiles.town` | `dim_town.town` |
| `indicative_profiles.flat_type` | `dim_flat_type.flat_type` |

**Design choices:**
- Measures only, never implicit aggregations: every column has `summarizeBy: none`. See DEC-027.
- Auto date/time is disabled: `__PBI_TimeIntelligenceEnabled = 0`. No time-intelligence functions are used, because the "latest 12 months" windows come from explicit `dim_month` flags computed in SQL against the last *full* month.
- Analysis and model result tables are linked only to the month, town or flat-type dimensions where that is meaningful. For example, the mix-adjusted index is all-market, so a town slicer correctly does *not* change it, and its visual says so.

## 4. DAX measures

This catalogue is generated from `build_pbip.MEASURES`. Validation values come from `dax_validation_results.csv`.

| Measure | Folder | DAX | Format | Meaning | Validated vs Python |
|---|---|---|---|---|---|
| **Transactions** | Market | `COUNTROWS ( fact_transactions )` | `#,0` | Number of registered resale transactions in the current filter context (includes the partial month). | no filter: expected 242,307 = actual 242,307 |
| **Transactions (Full Months)** | Market | `CALCULATE ( [Transactions], dim_month[is_partial_month] = 0 )` | `#,0` | Transactions excluding the still-accumulating latest month (DEC-008). | no filter: expected 241,557 = actual 241,557 |
| **Median Price** | Market | `MEDIAN ( fact_transactions[resale_price] )` | `\$#,0` | Median registered resale price (SGD). | evaluates without error (grand total) |
| **Median Price (Full Months)** | Market | `CALCULATE ( [Median Price], dim_month[is_partial_month] = 0 )` | `\$#,0` | Median price excluding the partial month; used for trends. | no filter: expected 505,000 = actual 505,000 |
| **Mean Price** | Market | `AVERAGE ( fact_transactions[resale_price] )` | `\$#,0` | Arithmetic mean price; shown for comparison only (skewed upward). | evaluates without error (grand total) |
| **P25 Price** | Market | `PERCENTILE.INC ( fact_transactions[resale_price], 0.25 )` | `\$#,0` | 25th percentile price (linear interpolation, same as pandas quantile). | evaluates without error (grand total) |
| **P75 Price** | Market | `PERCENTILE.INC ( fact_transactions[resale_price], 0.75 )` | `\$#,0` | 75th percentile price. | evaluates without error (grand total) |
| **Median Price per sqm** | Market | `MEDIAN ( fact_transactions[price_per_sqm] )` | `\$#,0` | Median of row-level price per square metre (SGD/sqm). | evaluates without error (grand total) |
| **Median Floor Area** | Market | `MEDIAN ( fact_transactions[floor_area_sqm] )` | `#,0` | Median floor area (sqm). | evaluates without error (grand total) |
| **Transactions Latest 12M** | Latest 12 months | `CALCULATE ( [Transactions], dim_month[is_latest_12m] = 1 )` | `#,0` | Transactions in the 12 full months ending at the last full month. | no filter: expected 24,658 = actual 24,658; town=BEDOK, flat_type=4 ROOM: expected 511 = actual 511 |
| **Median Price Latest 12M** | Latest 12 months | `CALCULATE ( [Median Price], dim_month[is_latest_12m] = 1 )` | `\$#,0` | Median price over the latest 12 full months. | no filter: expected 630,000 = actual 630,000; town=BEDOK, flat_type=4 ROOM: expected 593,000 = actual 593,000 |
| **Median Price Prior 12M** | Latest 12 months | `CALCULATE ( [Median Price], dim_month[is_prior_12m] = 1 )` | `\$#,0` | Median price over the 12 months before the latest 12. | no filter: expected 625,000 = actual 625,000 |
| **Median Price YoY %** | Latest 12 months | `VAR cur = [Median Price Latest 12M] VAR prev = [Median Price Prior 12M] RETURN IF ( NOT ISBLANK ( cur ) && NOT ISBLANK ( prev ), DIVIDE ( cur, prev ) - 1 )` | `0.0%` | Change in median price, latest 12 vs prior 12 full months. Raw median: includes changes in the mix of flats sold. | no filter: expected 0.008 = actual 0.008 |
| **P25 Price Latest 12M** | Latest 12 months | `CALCULATE ( [P25 Price], dim_month[is_latest_12m] = 1 )` | `\$#,0` | 25th percentile. | town=BEDOK, flat_type=4 ROOM: expected 529,500 = actual 529,500 |
| **P75 Price Latest 12M** | Latest 12 months | `CALCULATE ( [P75 Price], dim_month[is_latest_12m] = 1 )` | `\$#,0` | 75th percentile. | town=BEDOK, flat_type=4 ROOM: expected 815,944 = actual 815,944 |
| **Mean Price Latest 12M** | Latest 12 months | `CALCULATE ( [Mean Price], dim_month[is_latest_12m] = 1 )` | `\$#,0` | Mean price. | no filter: expected 661,706 = actual 661,706 |
| **Median Price per sqm Latest 12M** | Latest 12 months | `CALCULATE ( [Median Price per sqm], dim_month[is_latest_12m] = 1 )` | `\$#,0` | Median SGD per sqm. | town=BEDOK, flat_type=4 ROOM: expected 6,428.57 = actual 6,428.57 |
| **Sample Size Flag Latest 12M** | Latest 12 months | `IF ( [Transactions Latest 12M] < 30, "Low sample (n<30)", "OK" )` | `-` | Warns when a comparison rests on fewer than 30 sales. | evaluates without error (grand total) |
| **Data Coverage Text** | Context | `"Data: " & SELECTEDVALUE ( refresh_info[first_month] ) & " to " & SELECTEDVALUE ( refresh_info[last_full_month] ) & " (full months). Partial month excluded from trends: " & SELECTEDVALUE ( refresh_info[partial_month] ) & ". Retrieved " & SELECTEDVALUE ( refresh_info[retrieved_at_local] ) & " SGT."` | `-` | Coverage and refresh timestamp for report headers. | evaluates without error (grand total) |
| **Attribution Text** | Context | `SELECTEDVALUE ( refresh_info[attribution] )` | `-` | Data licence attribution (Singapore Open Data Licence v1.0). | evaluates without error (grand total) |
| **Raw Median Index** | Index | `MAX ( price_index_monthly[raw_median_index] )` | `0.0` | Raw monthly median price, 2017 = 100 (all flats; not affected by town/type slicers). | evaluates without error (grand total) |
| **Mix-Adjusted Index** | Index | `MAX ( price_index_monthly[mix_adjusted_index] )` | `0.0` | Hedonic time-dummy index for comparable flats, 2017 = 100 (DEC-017). | evaluates without error (grand total) |
| **Storey Premium vs Lowest Band** | Evidence | `MAX ( storey_effects_adjusted[pct_vs_reference] ) / 100` | `0.0%` | Adjusted price difference vs floors 01-03 (model M2, recent window). | evaluates without error (grand total) |
| **Lease Premium vs Shortest Band** | Evidence | `MAX ( lease_effects_adjusted[pct_vs_reference] ) / 100` | `0.0%` | Adjusted price difference vs the shortest remaining-lease band (model M2). | evaluates without error (grand total) |
| **Town Effect vs Ang Mo Kio** | Evidence | `MAX ( town_effects_adjusted[pct_vs_reference] ) / 100` | `0.0%` | Adjusted price difference vs Ang Mo Kio (model M1, recent window). | evaluates without error (grand total) |
| **Test MAE** | Model | `MAX ( model_comparison[mae] )` | `\$#,0` | Mean absolute error on the test year (SGD). | evaluates without error (grand total) |
| **Selected Model MAE (Static)** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Selected: gradient boosting (trained once)" )` | `\$#,0` | Test MAE of the selected model trained once before the test year. | evaluates without error (grand total) |
| **Selected Model MAE (Monthly Refit)** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Selected: gradient boosting (retrained monthly)" )` | `\$#,0` | Test MAE when retrained before each month. | evaluates without error (grand total) |
| **Selected Model Typical % Error** | Model | `CALCULATE ( MAX ( model_comparison[mdape_pct] ), model_comparison[model_label] = "Selected: gradient boosting (trained once)" ) / 100` | `0.0%` | Median absolute % error. | evaluates without error (grand total) |
| **Selected Model R2** | Model | `CALCULATE ( MAX ( model_comparison[r2] ), model_comparison[model_label] = "Selected: gradient boosting (trained once)" )` | `0.000` | R-squared on the test year. | evaluates without error (grand total) |
| **Baseline B2 MAE** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Baseline B2: town x type median, last 12 months" )` | `\$#,0` | Realistic baseline MAE. | evaluates without error (grand total) |
| **Error Reduction vs Baseline** | Model | `DIVIDE ( [Baseline B2 MAE] - [Selected Model MAE (Static)], [Baseline B2 MAE] )` | `0.0%` | Share of baseline error removed by the selected model. | evaluates without error (grand total) |
| **MAE Trained Once** | Model | `MAX ( model_errors_by_month[mae_static] )` | `\$#,0` | Test MAE by month, model trained once. | evaluates without error (grand total) |
| **MAE Retrained Monthly** | Model | `MAX ( model_errors_by_month[mae_monthly_refit] )` | `\$#,0` | Test MAE by month, model retrained monthly. | evaluates without error (grand total) |
| **MAE Baseline B2** | Model | `MAX ( model_errors_by_month[mae_B2_monthly_refit] )` | `\$#,0` | Test MAE by month, baseline B2 (monthly refit). | evaluates without error (grand total) |
| **MAE Increase When Shuffled** | Model | `MAX ( model_feature_importance[mae_increase_sgd] )` | `\$#,0` | Permutation importance (SGD). | evaluates without error (grand total) |
| **Profile Estimate** | Estimates | `MAX ( indicative_profiles[estimated_price_rounded] )` | `\$#,0` | Indicative estimate for a defined profile (pre-computed in Python; not live). | evaluates without error (grand total) |

**Filter-context notes:**
- *Latest 12M* measures override the month context through `dim_month[is_latest_12m] = 1`. Town, flat type, storey and model slicers still apply.
- `Median Price YoY %` is a **raw** median comparison, so it includes mix changes (see H5). It is labelled that way on page 1.
- `PERCENTILE.INC` matches pandas' default `quantile` (linear interpolation), which is why P25 and P75 validate exactly.
- Model and evidence measures use `MAX()` over one-row-per-category tables. With a single category in context, `MAX` returns that row's value. At a grand total it returns the largest value, so these measures are shown only in visuals that are split by category, or in cards filtered to one row through `CALCULATE`.

## 5. Pages

| Page | Purpose (brief §9) | Visuals | Slicers |
|---|---|---|---|
| 1 Market overview | Q1: volumes and price trend | 4 KPI cards (latest-12-month median, YoY %, transactions, price/sqm); monthly median line (full months); monthly transactions column (full months); median by flat type bar (n in tooltip); latest vs prior table by flat type; coverage and refresh line | Town, flat type |
| 2 Town & property | Q2: fair comparisons | Town table (n, median, P25, P75, price/sqm, low-sample flag), sorted by median; median by storey range; median by remaining-lease band (tooltips show n) | Flat type, town, floor-area band |
| 3 Price drivers & evidence | Q3: association, not causation | Hypothesis results table; raw vs mix-adjusted index; adjusted storey and lease premium curves; adjusted town effects; caveat text | None. The tables are pre-computed and the page text says so. |
| 4 Model performance | Q4: accuracy and reliability | 5 KPI cards (selected MAE static and monthly-refit, typical % error, baseline MAE, error reduction); MAE by model; MAE by test month (3 lines); segment error table; feature reliance; text on intervals withheld | Segment (flat type, town, flat model, storey, price quintile, month) |
| 5 Indicative estimates | Optional page (§8.7), implemented with pre-computed profiles | Profile table with estimate, typical % and SGD error, reliability label and segment median; disclaimer text | Town, flat type |

All pages are 1280 × 720. Each visual title states the population and window, and the coverage card at the bottom of pages 1–2 shows the data period and retrieval time.

## 6. Indicative estimates page: what it is and isn't

- **What it is:** a table of model estimates for pre-defined **typical** profiles (DEC-026).
  - There is one profile per town × flat type with at least 30 sales in the latest 12 months: 96 segments × 3 storey levels = 288 rows.
  - Each profile uses the segment's median floor area, lease commencement year and remaining lease, its most common flat model and street, and the last full month.
- **How it was estimated:** the selected model (DEC-024), refit on all full months.
- **Shown alongside each estimate:**
  - a typical error: the larger of the town and flat-type MdAPE in the monthly-refit test;
  - a reliability label;
  - the segment's actual median price, for context.
- **What it isn't:** live inference. Changing a slicer only filters the table, and the page text says so explicitly.
- **Known weakness:** when a segment mixes very different designs, the "most common model" can be atypical.
  - Example: Central Area 4-ROOM's modal model is Type S1, a premium design, which gives estimates 31–34% above the segment median.
  - These rows are labelled less reliable because their storey band rarely sells in that segment.
  - Overall, profile estimates vs segment medians have a median gap of −0.2%. By storey variant: low −5.2%, middle +0.5%, high +3.9%.

## 7. Validation procedure (repeat after any change)

1. `python -m pytest -q`. This includes the SQL-vs-pandas cross-check, band-edge parity with Python, DAX expected-value logic, and the visual-field-exists check.
2. `powershell -ExecutionPolicy Bypass -File powerbi/tools/validate_tmdl.ps1`. Expect `TMDL OK`.
3. Open the PBIP in Desktop, click Refresh, then run `powerbi/tools/query_model.ps1`. Expect `ALL CHECKS PASSED`.
4. Visual review checklist (§8).

## 8. Visual review checklist (manual, in Desktop)

These items need a person to look at the report:
- [ ] Every visual shows data; none shows an error or "can't display" icon.
- [ ] Titles and axis labels are readable, and nothing overlaps.
- [ ] Currency shows as `$` with thousands separators, and percentages show one decimal place.
- [ ] Flat types appear in room order and storey ranges in floor order.
- [ ] Slicers filter pages 1, 2 and 5 as described in §5.
- [ ] Page 3 and page 4 tables read correctly. In particular, H5's estimate is in percentage points, as its title says.
- [ ] Screenshots are captured for the README from the real report only.

The results of this checklist are recorded in §9.

## 9. Visual review results

*Pending the manual review in Power BI Desktop.*

## 10. Manual fallback (if a future Desktop version rejects the generated report)

The semantic model is the most robust part, being plain TMDL that Desktop's own parser accepts.
- If the report folder fails to open, delete `HDB Resale Market.Report/definition/pages/*` except `pages.json`, set `pageOrder` to `[]`, and rebuild visuals by hand following §5.
- Alternatively, start a new report in Desktop connected to the same semantic model.

The measures, relationships and data are unaffected.
