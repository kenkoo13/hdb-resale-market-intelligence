# Changelog

All notable changes to this project. Entries record work that was actually completed.

## [Unreleased]

### Added — Phase 4 (2026-10-12)
- `sql/01_fact_and_dimensions.sql`, `sql/02_aggregates.sql`: SQLite star schema and window-function medians.
- `src/reporting/build_bi_tables.py`: curated Power BI tables, with an exact SQL-vs-pandas cross-check, DAX expected values and refresh metadata.
- `src/modelling/profiles.py`: 288 pre-computed indicative profile estimates with typical-error and reliability labels.
- `src/reporting/build_pbip.py`: generated Power BI Project with a TMDL semantic model (17 tables, 9 relationships, 37 documented DAX measures) and a PBIR report (5 pages, 44 visuals).
- `powerbi/tools/validate_tmdl.ps1` (Power BI's own TMDL parser) and `query_model.ps1` (DAX vs Python through the Desktop engine).
- Verified in Power BI Desktop 2.158: the project opens, refresh succeeds, and 67/67 engine checks pass.
- `docs/BI_BUILD_GUIDE.md`; DEC-025 to DEC-028; 9 BI tests (111 total).

### Fixed — Phase 4
- The SQL cross-check tolerance was too loose (`np.allclose` relative 1e-5 let a SGD 1 difference pass). It is now an absolute 1e-6.
- TMDL measure descriptions now use `///` comments; Power BI's parser rejected a `description:` property.
- SQLite connections are closed (ResourceWarning).

### Added — Phase 3 (2026-10-12)
- Model design pre-specified in MODEL_CARD §1–6 before any training (`dc67c89`, addendum `0ff236e`).
- `src/modelling/`: feature sets with a leakage guard (`features.py`), the chronological split (`splits.py`), baselines B0/B1/B2 and the Ridge and HistGradientBoosting pipelines (`models.py`), metrics, segment errors and conformal intervals (`evaluate.py`), and the orchestrator with static and monthly-refit evaluation (`run_modelling.py`).
- `src/reporting/model_figures.py`: figures 10–14, which can be regenerated without retraining.
- The model card with full results; DEC-019 to DEC-024; 22 modelling tests (102 total).

### Fixed — Phase 3
- Figure 13 attached labels to the wrong bars (bars split across two plotting calls). It is now one call with shared positions, and was re-checked visually.
- Monthly-refit interval arrays lost their row index (found in the smoke run).
- `TargetEncoder(shuffle, random_state)` is deprecated in scikit-learn 1.9; replaced with a seeded `KFold`.

### Added — Phase 2 (2026-10-12)
- Pre-registered hypotheses H1–H5 (committed before execution in `f56b053`).
- `src/analytics/`: shared windows (`common.py`), descriptive statistics (`descriptive.py`), hedonic models M1/M2 with building-clustered errors and a mix-adjusted index (`hedonic.py`), hypothesis execution with Holm correction (`hypotheses.py`), and the orchestrator (`run_analysis.py`).
- `src/reporting/figures.py`: 9 figures in `outputs/figures/`.
- 21 CSV result tables plus `analysis_results.json` in `outputs/tables/`.
- 16 analytics tests (80 total), including recovery of known synthetic coefficients.
- Decisions DEC-015 to DEC-018. Hypothesis register results, metric dictionary §2–3, lineage, dictionary, testing and reproducibility updates.
- README "Findings so far".

### Added — Phase 1 (2026-10-12)
- `src/ingestion/datagov_client.py`: full-snapshot download through the data.gov.sg initiate/poll API, with retries, timeouts, a manifest (SHA-256, row count, publisher metadata) and atomic snapshot folders.
- `src/validation/schema.py`: source schema contract and blocking gates (header, zero rows, row-count drop).
- `src/transformation/parsers.py` and `clean.py`: strict parsers; quarantine (Q01–Q07) versus flag policy; derived fields.
- `src/validation/quality_report.py`: measured DQ report (`outputs/data_quality/`).
- `src/pipeline.py`: CLI orchestrator with publish-only-after-gates behaviour.
- 64 unit tests on a synthetic fixture.
- Docs: DATA_QUALITY, DATA_DICTIONARY, DATA_LINEAGE, METRIC_DICTIONARY (row-level fields), TESTING, REPRODUCIBILITY.
- Decisions DEC-010 to DEC-014.

### Changed
- DEC-009 is superseded by DEC-013. The 147 excess copies of a suspected 2017 duplicate-publication artefact (exact duplicates at SGD 468,000/470,000) are now quarantined, while all other duplicates are kept.
- DEC-007 (MIT licence) was confirmed by the repository owner.

### Fixed
- Ingestion rejected the HTTP 201 response from `initiate-download`. It now accepts any 2xx status (found in the first live run).

### Added — Phase 0 (2026-10-12)
- Verified the official data.gov.sg dataset `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`: metadata, bulk-download API, live schema, licence.
- Project plan (`docs/PROJECT_PLAN.md`) with scope, architecture, acceptance criteria and risks.
- Decision log DEC-001 to DEC-009.
- Repository skeleton, `.gitignore`, MIT code licence, data attribution (`DATA_LICENSE.md`), example config.
