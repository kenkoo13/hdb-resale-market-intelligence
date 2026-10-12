# Project Plan — HDB Resale Market Intelligence & Price Prediction

Status: **All phases (0–6) complete** (2026-10-12). Final report: [HANDOVER.md](HANDOVER.md). Later phases are planned here and their status is tracked in the table at the end.

## 1. Business question

How can Singapore HDB resale transaction data be turned into reliable, explainable price intelligence that helps users compare resale flats and understand the factors *associated with* price differences?

| # | Question | Primary deliverable |
|---|----------|---------------------|
| Q1 | How have resale prices and transaction volumes changed over time? | Monthly volume/median trend tables, figures, BI page 1 |
| Q2 | How do prices differ by town, flat type, floor area, storey range, flat model, and lease? | Segment summary tables with counts, BI page 2 |
| Q3 | Which observable characteristics are associated with price differences, and how strong is the evidence? | Hypothesis register + evidence table, BI page 3 |
| Q4 | How accurately can a model estimate prices within the data's coverage, and where is it less reliable? | Model card, chronological evaluation, segment errors, BI page 4 |

This is an analytical study. It is **not** an official valuation tool, and model outputs are indicative estimates only.

## 2. Phase 0 findings (verified 2026-10-12)

### 2.1 Environment

| Item | Observed |
|------|----------|
| OS | Windows 11 Home 10.0.26200 |
| Project folder | New. Git repository initialised on `main`, no commits. The folder sits under OneDrive. |
| Git remote | `origin` = `https://github.com/kenkoo13/hdb-resale-market-intelligence.git`. `git ls-remote` succeeds and returns no refs, so the remote exists and is empty. |
| GitHub CLI | Not installed |
| Python | 3.14.4 (`C:\Python314`). A project virtual environment is created at `.venv/`. |
| Dependency wheels | A dry-run install shows binary wheels for Python 3.14 exist for pandas, numpy, scikit-learn 1.9.1, scipy 1.18.1, statsmodels 0.15.0, matplotlib 3.11.2, and pyarrow 26.0.0. |
| Power BI Desktop | Installed, version 2.158.1304.0 (September 2026 release). This supports the Power BI Project (PBIP / TMDL) format. |

### 2.2 Official source verification

| Item | Observed value | How verified |
|------|----------------|--------------|
| Dataset | Resale flat prices based on registration date from Jan-2017 onwards | `GET https://api-production.data.gov.sg/v2/public/api/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/metadata` |
| Dataset ID | `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` | Same |
| Publisher | Housing & Development Board (`managedBy`) | Same |
| Last updated | 2026-10-12T02:10:19+08:00 | Same |
| Declared coverage | 2017-01-01 to 2026-10-01 | Same |
| Format / size | CSV, 23,983,413 bytes | Same |
| Bulk download | `GET https://api-open.data.gov.sg/v1/public/api/datasets/{id}/initiate-download`, then `.../poll-download`. This returns a time-limited signed S3 URL to the full CSV (expires 3,600 s). | Executed successfully, and a 23,982,280-byte CSV was downloaded. |
| Fallback API | `GET https://data.gov.sg/api/action/datastore_search?resource_id={id}` (paginated). It reported `total` = 242,454. | Executed |
| Licence | Singapore Open Data Licence v1.0 (https://data.gov.sg/open-data-licence). It allows commercial and non-commercial use with attribution, and forbids implying official status or endorsement. | Licence page read |

**Source notes (from metadata, quoted in summary):** the floor area is approximate and includes recess areas, upgrading additions, and roof terraces. Transactions that may not reflect full market price (for example, resale between relatives or of part shares) are excluded. Resale prices are indicative only.

### 2.3 Live schema (declared vs observed)

| Field | Declared type (metadata) | Observed in CSV | Implication |
|-------|-------------------------|-----------------|-------------|
| month | Month (YYYY-MM) | 118 distinct, 2017-01 to 2026-10 | Parse as month and validate the format |
| town | Text | 26 values | Categorical |
| flat_type | Text | 7 values, including `MULTI-GENERATION` (n = 91) and `1 ROOM` (n = 89) | Sparse categories need care |
| block | Text | 2,788 values, alphanumeric | Keep as text |
| street_name | Text | 580 values | High-cardinality location |
| storey_range | Text | 17 three-storey bands, `01 TO 03` … `49 TO 51` | Parse lower/upper/mid storey |
| floor_area_sqm | **Text** | All values numeric, 31 to 366.7 | Parse safely and validate |
| flat_model | Text | 21 values, mixed case | Categorical. Sparse levels need grouping. |
| lease_commence_date | **Text** | Year values, 1966 to 2023 | Parse as integer year |
| remaining_lease | Text | 3 formats: `N years N months` (202,948), `N years` (19,889), `N years N month` (19,617) | A dedicated parser is needed. It is not numeric. |
| resale_price | Numeric | All numeric, SGD 140,000 to 1,728,000 | Prediction target |

### 2.4 Early data observations (exploratory, not findings)

- **Partial latest month:** 2026-10 has 750 rows, compared with about 2,100–2,650 a month for 2026-05 to 2026-09. The dataset is keyed by *registration* date, so the current month is still accumulating. It must be flagged and excluded from trend and model evaluation.
- **Exact duplicate rows:** 318 rows duplicate another row on all 11 fields. There is no transaction ID, so these could be genuine separate sales of near-identical units, for example in the same block and storey band in the same month. They must be investigated, not deleted blindly.
- **No blanks** in any field in this snapshot. Validation must still handle blanks in future refreshes.

## 3. Scope

**In scope:**
- A single-source pipeline: ingestion, validation, cleaning, a quarantine for unsafe records, and curated tables.
- Descriptive analysis that separates price change from mix change.
- A small pre-registered hypothesis set with effect sizes.
- A baseline, a linear model, and a tree-based model with chronological validation.
- Segment error analysis.
- A Power BI semantic model and report (or a full manual build package).
- Tests, documentation registers, and a GitHub-ready repository.

**Out of scope:**
- Any other HDB dataset (2012–2014, 2015–2016, or earlier), geocoding, MRT or school distances, macroeconomic data, or any other external enrichment.
- Official valuation and forecasting of future prices.
- Automated scheduled refresh. Refresh is a documented manual command.

## 4. Key assumptions (to be validated in Phase 1)

1. Each row is one registered resale transaction. There is no unique identifier.
2. `month` is the registration month, not the option or completion date.
3. `remaining_lease` is as recorded by HDB at the time of the transaction. Its format varies.
4. A full-snapshot download on each refresh is preferable to incremental retrieval, because there is no stable record key and no change feed.

## 5. Architecture (planned)

```
data.gov.sg API ──► src/ingestion (download full CSV, manifest: timestamp, sha256, schema, row count)
                      │   data/raw/<snapshot_id>/resale_raw.csv   (immutable, git-ignored)
                      ▼
                 src/validation (schema contract, type/format/range checks, quarantine)
                      ▼
                 src/transformation (typed, cleaned, flagged, engineered fields)
                      │   data/processed/transactions_clean.parquet
                      ▼
          ┌───────────┼──────────────────────────┐
   src/analytics   src/modelling             sql/ + SQLite
   (EDA, tests)    (baseline, linear, GBM)   (curated aggregate tables, cross-checks)
          └───────────┼──────────────────────────┘
                      ▼
          outputs/{figures,tables,model_metrics}  +  data/curated/*.csv (Power BI import)
                      ▼
                 powerbi/ (PBIP project and/or build guide)
```

The last successful outputs are only replaced after all validation gates pass (DEC-006).

## 6. Phases and acceptance criteria

| Phase | Deliverables | Acceptance criteria | Status |
|-------|-------------|---------------------|--------|
| 0 Inspect & plan | This plan, decision log, docs skeleton, licence/attribution, `.gitignore` | Source verified live. Environment recorded. Decisions logged. | Done |
| 1 Ingestion & DQ | `src/ingestion`, `src/validation`, `src/transformation`, quarantine, DQ report, unit tests | The pipeline runs end to end from the API. DATA_QUALITY.md reports actual counts. Tests pass. | Done (2026-10-12) |
| 2 EDA & hypotheses | Descriptive tables and figures, mix-adjusted view, hypothesis tests with effect sizes | The register is complete with actual results. Exploratory work is labelled. | Done (2026-10-12) |
| 3 Modelling | Baseline, linear, and tree model. Chronological train/validation/test split plus rolling backtest. Segment errors. Model card. | Test set used once. Leakage tests pass. Metrics recorded with dates and sample sizes. | Done (2026-10-12) |
| 4 BI | Curated tables, data model, DAX measures with validation values, report or build guide | DAX expected values match Python/SQL. No fake PBIX. | Done (2026-10-12) |
| 5 E2E verification | Clean-environment rerun, test run, docs consistency review | Commands in REPRODUCIBILITY.md work as written. | Done (2026-10-12) |
| 6 Portfolio readiness | README with real findings, screenshots of real work, handover | A hiring manager can assess the project without a walkthrough. | Done (2026-10-12) |

## 7. Risks

| Risk | Mitigation |
|------|-----------|
| The source schema changes or the API is unavailable | Schema contract check fails loudly. The last valid outputs are kept. No substitute source is used. |
| Strong price inflation in 2020–2025 makes chronological extrapolation hard | Time-aware validation, rolling backtests, and explicit reporting of drift error |
| Sparse categories (1 ROOM, MULTI-GENERATION, rare flat models, high storeys) | Report counts, apply minimum-sample rules, and label results as less reliable |
| A PBIX cannot be produced programmatically | Author a PBIP (text format) and verify it opens in Desktop, or fall back to a manual build guide |
| Python 3.14 is very new | Pin exact versions and record the freeze in `requirements.txt` |
| The folder is under OneDrive | `.venv` and data are git-ignored. OneDrive sync of `.venv` is a local nuisance only. |

## 8. Deviations from the suggested repository structure (brief §6)

| Suggested | Actual | Reason |
|---|---|---|
| `notebooks/` | Removed | All analysis runs as tested, reproducible modules (`src/analytics`, `src/modelling`) rather than notebooks, which are harder to test and to diff. Figures and tables are regenerated by commands. |
| — | `powerbi/tools/` | PowerShell scripts that validate the model with Power BI Desktop's own engine |
| — | `docs/DASHBOARD_GLOSSARY.md`, `docs/HANDOVER.md`, `docs/screenshots/` | Plain-language glossary (DEC-030), handover report and genuine report screenshots |
| `outputs/models/` (implied) | Git-ignored | Model binaries are reproducible from code + seed (DEC-004) |
