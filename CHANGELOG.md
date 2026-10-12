# Changelog

All notable changes to this project. Entries record work that was actually completed.

## [Unreleased]

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
