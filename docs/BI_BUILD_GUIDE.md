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
| Visuals render as intended (layout, formatting, readability) | **Verified by manual visual review**: 5 review rounds, all issues fixed (§9) | Screenshots of the real report in `docs/screenshots/` |
| A `.pbix` file | **Not produced by code**. Save it from Desktop (*File → Save as → .pbix*) if a single file is needed. | — |

## 2. How to open and refresh

1. Run the pipeline so the CSVs exist:
   `python -m src.pipeline` → `python -m src.analytics.run_analysis` → `python -m src.modelling.run_modelling` → `python -m src.reporting.build_bi_tables` → `python -m src.reporting.build_pbip --local-path`
2. Open `powerbi/HDB Resale Market.pbip` in Power BI Desktop.
3. **Point the report at your data folder.** The committed project uses a placeholder path (DEC-029). Either go to *Transform data → Edit parameters → CuratedFolder* and enter the absolute path of `data/curated/`, ending with `\`, or run `python -m src.reporting.build_pbip --local-path` to write your path into the project. Do not commit the `--local-path` version; `tests/test_bi.py` will fail as a reminder.
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
| **Sample Size Flag Latest 12M** | Latest 12 months | `IF ( [Transactions Latest 12M] < 30, "Too few (under 30)", "Yes" )` | `-` | Warns when a comparison rests on fewer than 30 sales (shown as 'Enough sales?'). | evaluates without error (grand total) |
| **Data Coverage Text** | Context | `"Data covers " & SELECTEDVALUE ( refresh_info[first_month_label] ) & " to " & SELECTEDVALUE ( refresh_info[last_full_month_label] ) & " (complete months). " & SELECTEDVALUE ( refresh_info[partial_month_label] ) & " is still being recorded and is left out of trends. Data downloaded " & SELECTEDVALUE ( refresh_info[retrieved_label] ) & "."` | `-` | Coverage and refresh timestamp for report headers. | evaluates without error (grand total) |
| **Attribution Text** | Context | `SELECTEDVALUE ( refresh_info[attribution] )` | `-` | Data licence attribution (Singapore Open Data Licence v1.0). | evaluates without error (grand total) |
| **Raw Median Index** | Index | `MAX ( price_index_monthly[raw_median_index] )` | `0.0` | Raw monthly median price, 2017 = 100 (all flats; not affected by town/type slicers). | evaluates without error (grand total) |
| **Mix-Adjusted Index** | Index | `MAX ( price_index_monthly[mix_adjusted_index] )` | `0.0` | Hedonic time-dummy index for comparable flats, 2017 = 100 (DEC-017). | evaluates without error (grand total) |
| **Storey Premium vs Lowest Band** | Evidence | `MAX ( storey_effects_adjusted[pct_vs_reference] ) / 100` | `0.0%` | Adjusted price difference vs floors 01-03 (model M2, recent window). | evaluates without error (grand total) |
| **Lease Premium vs Shortest Band** | Evidence | `MAX ( lease_effects_adjusted[pct_vs_reference] ) / 100` | `0.0%` | Adjusted price difference vs the shortest remaining-lease band (model M2). | evaluates without error (grand total) |
| **Town Effect vs Ang Mo Kio** | Evidence | `MAX ( town_effects_adjusted[pct_vs_reference] ) / 100` | `0%` | Adjusted price difference vs Ang Mo Kio (model M1, recent window). | evaluates without error (grand total) |
| **Test MAE** | Model | `MAX ( model_comparison[mae] )` | `\$#,0` | Mean absolute error on the test year (SGD). | evaluates without error (grand total) |
| **Selected Model MAE (Static)** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Chosen model (not updated)" )` | `\$#,0` | Test MAE of the selected model trained once before the test year. | evaluates without error (grand total) |
| **Selected Model MAE (Monthly Refit)** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Chosen model (updated monthly)" )` | `\$#,0` | Test MAE when retrained before each month. | evaluates without error (grand total) |
| **Selected Model Typical % Error** | Model | `CALCULATE ( MAX ( model_comparison[mdape_pct] ), model_comparison[model_label] = "Chosen model (not updated)" ) / 100` | `0.0%` | Median absolute % error. | evaluates without error (grand total) |
| **Selected Model R2** | Model | `CALCULATE ( MAX ( model_comparison[r2] ), model_comparison[model_label] = "Chosen model (not updated)" )` | `0.000` | R-squared on the test year. | evaluates without error (grand total) |
| **Baseline B2 MAE** | Model | `CALCULATE ( [Test MAE], model_comparison[model_label] = "Simple benchmark (recent typical price)" )` | `\$#,0` | Realistic baseline MAE. | evaluates without error (grand total) |
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

All visible wording follows [DASHBOARD_GLOSSARY.md](DASHBOARD_GLOSSARY.md), which maps each plain-language label to its technical term (DEC-030).

| Page (as shown) | Business question | Visuals (plain-language labels) | Filters |
|---|---|---|---|
| 1 Market overview | How are HDB resale prices and sales changing? | 4 KPI cards (typical price, price change vs previous 12 months, flats sold, typical price per sqm); typical price each month; flats sold each month; typical price by flat type; this year vs last year table; data coverage line | Town, flat type |
| 2 Compare towns & flats | What do similar flats sell for? | Prices by town table (flats sold, typical price, low end, high end, price per sqm, enough sales?); typical price by floor level; typical price by years of lease left | Flat type, town, flat size |
| 3 What drives prices | What drives price differences between otherwise similar flats? | Key findings table (question, what the data shows, size of effect, likely range, evidence); headline vs like-for-like price trend; extra paid for higher floors; extra paid for more lease left; town price level vs Ang Mo Kio; how-to-read note | None. The results are fixed calculations and the page says so. |
| 4 Estimate accuracy | How accurate are the estimates, and where are they less reliable? | 5 KPI cards (average prediction error, typical error %, average error with monthly updates, error using a simple benchmark, reduction in prediction error); accuracy by approach; does accuracy worsen over time; where predictions are less accurate (table); which factors influence predictions; how-we-tested note | Break down by (flat type, town, flat model, floor level, price level, month) |
| 5 Estimated prices | What might a typical flat cost? | Estimated price of a typical flat per town and flat type at three floor levels, with typical error, recent typical price and reliability; how-to-read note | Town, flat type |

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
  - These rows are labelled "Lower: this floor level is rarely sold here", because their floor level rarely sells in that segment.
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

| Review | Date | Findings | Action |
|---|---|---|---|
| 1 (layout) | 2026-10-12 | All 44 visuals rendered with data, but: KPI values clipped; slicers too short (no dropdown); coverage text oversized; wide tables hid columns, including page 5's reliability column; raw number formats; missing reference bands on the effect curves; similar series colours | Fixed in the generator: card, slicer and table sizing; display names and formats; reference rows; explicit series colours |
| 2 (layout) | 2026-10-12 | Layout correct: values, dropdowns, columns and coverage line fully visible | None |
| 3 (wording) | 2026-10-12 | About 120 text elements audited for a non-technical business audience | All labels rewritten in plain language (DASHBOARD_GLOSSARY.md §2); calculations unchanged; DAX re-validated |
| 4 (business-reader check) | 2026-10-12 | Page 3: only 4 of 5 findings visible; floor and lease curves needed sideways scrolling; town axis truncated. Page 4: simple benchmark bar hidden; reliability column clipped | Auto-generated chart subtitles switched off; findings ordered by question; floor and lease curves on a numeric axis; town bars labelled directly; page 4 rows rebalanced |
| 5 (final) | 2026-10-12 | All content visible. One ambiguity remained: flat model "2-room" vs flat type "2 ROOM" in the same list | Redundant "Grouping" column removed; flat-model groups prefixed "Model:". The prefix was verified by querying the refreshed report's engine, so the page 4 screenshot predates it. All 67 engine checks passed. |

Screenshots of the real report are in `docs/screenshots/`.

## 10. Manual fallback (if a future Desktop version rejects the generated report)

The semantic model is the most robust part, being plain TMDL that Desktop's own parser accepts.
- If the report folder fails to open, delete `HDB Resale Market.Report/definition/pages/*` except `pages.json`, set `pageOrder` to `[]`, and rebuild visuals by hand following §5.
- Alternatively, start a new report in Desktop connected to the same semantic model.

The measures, relationships and data are unaffected.
