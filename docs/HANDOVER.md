# Handover Report — HDB Resale Market Intelligence & Price Prediction

**Date:** 2026-10-12. **Version:** 1.0.0. **Snapshot:** `20261012T010041Z`.

This report separates **verified** work (executed and checked) from planned or incomplete work. Every figure comes from committed outputs; `tests/test_docs_consistency.py` checks the key ones automatically.

---

## A. Deliverables

| Area | Files | Status |
|---|---|---|
| Ingestion and validation | `src/ingestion/datagov_client.py`, `src/validation/schema.py`, `src/validation/quality_report.py`, `src/pipeline.py` | Verified against the live API |
| Cleaning | `src/transformation/parsers.py`, `clean.py` | Verified |
| Analysis | `src/analytics/` (descriptive, hedonic, hypotheses, orchestrator) | Verified |
| Modelling | `src/modelling/` (features, splits, models, evaluation, profiles, orchestrator) | Verified |
| SQL | `sql/01_fact_and_dimensions.sql`, `sql/02_aggregates.sql` | Verified (exact parity with pandas) |
| Reporting | `src/reporting/figures.py`, `model_figures.py`, `build_bi_tables.py`, `build_pbip.py` | Verified |
| Power BI | `powerbi/HDB Resale Market.pbip`, `.SemanticModel` (TMDL), `.Report` (PBIR); `powerbi/tools/validate_tmdl.ps1`, `query_model.ps1` | Verified in Power BI Desktop 2.158 |
| Analytical outputs | `outputs/data_quality/`, `outputs/tables/` (21 CSVs + JSON), `outputs/model_metrics/`, `outputs/figures/` (14 PNGs) | Committed |
| BI import tables | `data/curated/` (the fact table is regenerated; small tables are committed) | Committed |
| Model artefact | `outputs/models/selected_model.joblib` | Reproducible, git-ignored (DEC-004) |
| Tests | `tests/` (121 tests, synthetic fixtures) | 121 passed |
| Documentation | README, CHANGELOG, LICENSE, DATA_LICENSE, and `docs/`: PROJECT_PLAN, DECISION_LOG (DEC-001..031), DATA_DICTIONARY, DATA_LINEAGE, DATA_QUALITY, HYPOTHESIS_REGISTER, METRIC_DICTIONARY, MODEL_CARD, BI_BUILD_GUIDE, DASHBOARD_GLOSSARY, TESTING, REPRODUCIBILITY, HANDOVER | Complete |
| Screenshots | `docs/screenshots/page1–5.png` | Genuine screenshots of the real report |

## B. Data quality

- **Source:** HDB, data.gov.sg `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`, last updated 2026-10-12 02:10 SGT. Coverage: Jan 2017 – Sep 2026 complete, plus a partial Oct 2026.
- **Rows:**
  - 242,454 raw;
  - 147 quarantined (suspected 2017 duplicate-publication artefact; reason code Q07);
  - 242,307 clean;
  - 750 in the partial month;
  - **241,557 analysis-ready**.
- **Field checks:** 0 blank values and 0 parse failures across all 11 fields. No missing months.
- **Remaining lease:** three text formats, all parsed. It agrees with the lease start year within the expected 0–1 year; 1 inconsistent row is flagged.
- **Limitations:**
  - there is no transaction ID, so duplicate handling relies on evidence (DEC-013 is provisional);
  - prices are by registration month;
  - floor area includes extensions;
  - storey is a band;
  - late-registration behaviour can't be measured from a single snapshot (DEC-008 is provisional).

Details: [DATA_QUALITY.md](DATA_QUALITY.md).

## C. Analytical findings (executed; associations, not causes)

| ID | Finding | Evidence |
|---|---|---|
| H1 | +7.8% per 10 floors for otherwise similar flats (CI 7.5–8.0%) | Supported, robust |
| H2 | +10.6% per 10 years of remaining lease (CI 10.3–10.9%); non-linear, steepest below about 60 years | Supported, robust. Mixes lease with building age and condition. |
| H3 | +9.3% per 10 sqm within a flat type (CI 8.9–9.7%) | Supported, robust |
| H4 | Town strongly differentiates 4-ROOM prices (ε² = 0.42); about 61 points of spread after controls | Supported. The p-value is optimistic because sales within a building are not independent. |
| H5 | Raw median +53.7% vs like-for-like +57.4% since 2017: the headline understates growth by 3.7 points | Material composition effect |

The hypotheses were pre-registered (commit `f56b053`), Holm-corrected, and tested against a 2% practical threshold. Details: [HYPOTHESIS_REGISTER.md](HYPOTHESIS_REGISTER.md).

## D. Model results

**Split:**
- train: Jan 2017 – Sep 2024 (190,655);
- validation: Oct 2024 – Sep 2025 (26,244);
- test: Oct 2025 – Sep 2026 (24,658), evaluated once.

| Model | Test MAE (SGD) | MdAPE | R² |
|---|---:|---:|---:|
| B0 global median | 206,703 | 25.9% | −0.64 |
| B1 town × type median, all history | 160,130 | 21.4% | 0.14 |
| B2 town × type median, last 12 months | 84,509 | 8.8% | 0.64 |
| Ridge (+ street) | 46,280 | 5.5% | 0.91 |
| **Gradient boosting + street (selected), static** | **27,578** | **3.2%** | **0.966** |
| Selected, monthly refit | 25,387 | 3.0% | 0.972 |

**Segment limitations:**
- MAE rises about 40% over 12 months without retraining;
- rare types and models (1 ROOM n = 9, MULTI-GENERATION n = 6, Terrace n = 10) have 5–10% MdAPE;
- Marine Parade 5.5%;
- streets new in the test year: 4.2% vs 3.2%;
- cheap flats are over-estimated (+2.7%) and expensive ones under-estimated (−1.8%).

**Intervals:** 80% conformal intervals covered 65% of test prices, so they are withheld (DEC-023). Details: [MODEL_CARD.md](MODEL_CARD.md).

## E. Power BI status

- **A valid Power BI Project (PBIP) was created and tested.** It is not a `.pbix`; one can be saved from Desktop.
- **Verified in Power BI Desktop 2.158:**
  - the TMDL parses with Desktop's own serializer;
  - the project opens and refreshes;
  - **13/13 DAX values equal the Python results**, 37/37 measures evaluate, and 17/17 row counts match;
  - five rounds of visual review were completed, and all issues found were fixed;
  - all text is in plain business language.
- **Manual steps for another user:**
  1. Set the `CuratedFolder` parameter, or run `build_pbip --local-path`.
  2. Click **Refresh**.

  The committed project uses a placeholder path (DEC-029).
- **Last-mile caveat:** the final label tweak ("Model: 2-room") was verified by querying the engine. The page 4 screenshot was taken just before it.

## F. Documentation coverage

All registers and guides listed in the brief exist and agree with the code. Agreement is enforced by tests for the documented figures and the DAX catalogue. Remaining gaps:
- **Profile reliability rule:** the definition of "rarely sold" (fewer than 10 sales of that floor band in the segment) is documented in `profiles.py` and the BI guide, but not as its own decision entry.
- **Plausibility bounds:** the bounds in DEC-011 are judgement-based; this is stated in the entry.
- **No other material decision or calculation is known to be undocumented.**

## G. Test status

| Suite | Result |
|---|---|
| `pytest -q` (2026-10-12, Python 3.14.4) | **121 passed, 0 failed, 0 skipped** |
| Clean-room clone (`0829184`) | 113/113 passed (the suite at that commit) |
| Power BI engine checks (`query_model.ps1`) | 67/67 passed |
| TMDL parse (`validate_tmdl.ps1`) | OK |
| Mutation checks | Data rules: 7 failures on 2 injected defects. Documentation tests: 2 failures on 2 injected errors. SQL cross-check: detected a SGD 1 tamper after a tolerance bug was fixed. |

**Not executed:** tests on Python 3.12 or 3.13, macOS or Linux; a refresh in which the source had genuinely new rows (the source was unchanged on the test day).

## H. Reproducibility

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lock.txt
.venv/Scripts/python -m src.pipeline
.venv/Scripts/python -m src.analytics.run_analysis
.venv/Scripts/python -m src.modelling.run_modelling
.venv/Scripts/python -m src.reporting.build_bi_tables
.venv/Scripts/python -m src.reporting.build_pbip --local-path
.venv/Scripts/python -m pytest -q
```

- **Same raw snapshot:** the outputs are identical, except wall-clock timings (verified in the Phase 5 clean room).
- **Newer snapshot:** the figures will differ, and the documentation tests skip with a reason until the narrative is updated.
- **Settings:** seed 42; Python ≥ 3.12.

## I. GitHub status

- **Published.** `main` was pushed on 2026-10-12, with the owner's approval, to the public repository https://github.com/kenkoo13/hdb-resale-market-intelligence. The published head was verified identical to the local head; there are 11 commits.
- **Remote:** `origin` = `https://github.com/kenkoo13/hdb-resale-market-intelligence.git` (public). It was empty before the first push, so nothing was overwritten.
- **Privacy:** before the first push, at the owner's request, the commit history was rewritten so that every commit uses the owner's GitHub no-reply address. Content was verified identical before and after the rewrite.

## J. Outstanding issues and next steps

1. **Optional:** add a short repository description and topics on GitHub (for example: data-analytics, power-bi, python, singapore, housing).
2. **DEC-013 (2017 duplicates):** ask HDB or data.gov.sg to confirm. Watch `Q07` in future snapshots.
3. **DEC-008 (partial month):** compare month counts across snapshots to see whether late registrations affect the month before the latest.
4. **Model:**
   - try a higher boosting iteration cap (chosen on validation);
   - add multi-year rolling backtests;
   - develop an interval method that holds coverage under market drift (adaptive conformal), validated across regimes.
5. **Wider testing:** run on Python 3.12/3.13 and Linux; add CI (GitHub Actions) to run `pytest` on each push.
6. **Refresh:** HDB updates daily. Rerun the pipeline, review the narrative docs, then update `DOCUMENTED_SNAPSHOT`. There is no automated schedule (DEC-003).
