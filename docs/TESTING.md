# Testing

## How to run

```bash
.venv/Scripts/python -m pytest -q        # Windows
.venv/bin/python -m pytest -q            # macOS / Linux
```

Unit tests use **synthetic data only** (`tests/fixtures/`, see its README) and never call the network. HTTP is replaced by a fake session.

## Coverage by requirement

| Requirement (brief §11) | Tests | Status |
|---|---|---|
| Source schema validation | `test_schema.py` (8): missing, renamed, extra, reordered and duplicate columns; declared-type change | Implemented |
| Missing and invalid value handling | `test_clean.py`: Q01, Q02, Q03, Q05, invalid lease kept and flagged; `test_parsers.py`: blanks | Implemented |
| Numeric parsing | `test_parsers.py::test_parse_decimal_*` (zero vs missing, rejects `1,000`, `1e5`, `inf`, signs) | Implemented |
| Date parsing | `test_parsers.py::test_parse_month_valid_and_invalid` | Implemented |
| Lease parsing | `test_parsers.py::test_parse_remaining_lease_*` (all 3 observed formats plus invalid forms) | Implemented |
| Deduplication logic | `test_clean.py::test_genuine_duplicate_kept_and_annotated`, `test_2017_artefact_keeps_first_copy` | Implemented |
| Feature-engineering formulas | `test_clean.py::test_derived_fields` (price/sqm, lease months, derived lease, storey midpoint) | Phase 1 fields done; model features in Phase 3 |
| Analysis methods (Phase 2) | `test_analytics.py` (16): the hedonic model recovers known synthetic coefficients inside their CIs; % conversion; the month index recovers a known trend; the delta-method period change matches its definition and covers the truth; reference-level handling; segment statistics (median, quartile, low-sample flag); ε²; the decision rule matches the register for all 5 outcome types; band edges | Implemented |
| Prevention of target leakage | `test_modelling.py`: forbidden columns rejected (target, log target, price/sqm, row number, duplicate size, block, DQ flags); feature sets clean; **the target encoder is unaffected by tenfold-inflated validation prices** | Implemented |
| Chronological split behaviour | `test_split_is_chronological_and_disjoint`, `test_split_rejects_partial_month`, `test_time_index` | Implemented |
| Model metric calculations | `test_metrics_hand_computed` (MAE, RMSE, R², MedAE, MdAPE, bias against hand calculation); conformal coverage ≈ 80% on exchangeable synthetic data; reliability flag | Implemented |
| Baselines, unseen categories, selection rule | B0/B1/B2 fallbacks and recent window; unseen town, model and street do not crash either model; models beat the baseline on synthetic signal; 1% tie-break prefers the simpler model | Implemented |
| Data output schemas | `test_pipeline.py::test_outputs_written_with_expected_schema` | Processed outputs done; curated BI outputs in Phase 4 |
| Refresh failure handling | `test_ingestion.py` (retry, exhausted retries, 4xx, API error code, wrong dataset, poll timeout, download error; no partial snapshot left behind); `test_pipeline.py` (schema change and row-count collapse leave previous outputs byte-identical) | Implemented |
| Idempotent refresh | `test_clean.py::test_idempotent`, `test_pipeline.py::test_reprocessing_same_snapshot_is_idempotent` | Implemented |
| Python/SQL vs Power BI consistency | — | Phase 4 |

## Recorded results

| Date | Environment | Command | Result |
|---|---|---|---|
| 2026-10-12 | Windows 11, Python 3.14.4, `requirements-lock.txt` | `python -m pytest -q` | **64 passed**, 0 failed, 0 skipped (parsers 25, clean 19, schema 8, ingestion 8, pipeline 4) |
| 2026-10-12 (Phase 2) | same | `python -m pytest -q` | **80 passed**, 0 failed, 0 skipped (adds analytics 16) |
| 2026-10-12 (Phase 3) | same | `python -m pytest -q` | **102 passed**, 0 failed, 0 skipped (adds modelling 22). On first run 2 new tests failed because of **test** errors: a wrong hand-computed median, and an unrealistic 13–24-month horizon. Both were corrected and explained in the Phase 3 notes; the model code was unchanged. |

### Mutation check (do the tests detect real defects?)
On 2026-10-12 two deliberate defects were introduced into `clean.py`: the artefact year was changed to 2018, and the partial-month comparison was changed from `>=` to `>`. Result: **7 tests failed**, as intended. The code was then restored and all 64 tests passed again.

## Integration check against the live source (not part of the automated suite)
`python -m src.pipeline` was run on 2026-10-12 against the real API. During the run:
- The bulk download returned HTTP 201 on `initiate-download`, which exposed a bug: only 200 was accepted. It was fixed by accepting any 2xx.
- A real HTTP 429 (rate limit) on `poll-download` was retried successfully.

The run completed with all gates passed. The live API is deliberately left out of `pytest` so the tests stay deterministic and work offline.
