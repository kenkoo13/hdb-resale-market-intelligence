# Reproducibility

## Environment

| Item | Tested with |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| Python | 3.14.4 (tested). The pinned libraries require **≥ 3.12** (scipy 1.18); 3.12 and 3.13 are untested. |
| Dependencies | `requirements.txt` (direct, pinned); `requirements-lock.txt` (full freeze) |
| Network | Required only to download the source data. No API key is needed. |
| Random seed | 42 (`config/project_config.example.yaml`; used from Phase 3) |

## Setup

```bash
git clone https://github.com/kenkoo13/hdb-resale-market-intelligence.git
cd hdb-resale-market-intelligence
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lock.txt   # exact tested environment (recommended)
# .venv/bin/python -m pip install -r requirements-lock.txt     # macOS / Linux
# requirements.txt pins only direct dependencies; resolving from it may pick different
# transitive versions (Phase 5 clean-room install resolved wrapt 2.5.1rc1 instead of 2.5.0).
```

Optional: copy `config/project_config.example.yaml` to `config/project_config.yaml` to change timeouts or thresholds. The defaults need no configuration.

## Run

| Step | Command | Expected output |
|---|---|---|
| Download and process the latest snapshot | `.venv/Scripts/python -m src.pipeline` | `data/raw/<UTC timestamp>/`, `data/processed/*`, `outputs/data_quality/*`. Run info is printed as JSON. Exit code 0. |
| Reprocess the latest snapshot without downloading | `.venv/Scripts/python -m src.pipeline --skip-download` | Same outputs. For the same snapshot the data content is identical; only the processing timestamp in `run_info.json` changes. |
| Reprocess a specific snapshot | `.venv/Scripts/python -m src.pipeline --snapshot 20261012T010041Z` | — |
| Analysis: descriptive stats, hypotheses, figures | `.venv/Scripts/python -m src.analytics.run_analysis` | `outputs/tables/*.csv`, `analysis_results.json`, `outputs/figures/*.png`. Took 2.5–5 minutes across runs on the test machine (12 logical CPUs, 7.8 GB RAM), mostly the full-period hedonic fit and VIF. Peak memory was not measured. |
| Modelling: train, select, evaluate | `.venv/Scripts/python -m src.modelling.run_modelling` | `outputs/model_metrics/*`, figures 10–14, `data/processed/model_test_predictions.parquet`, `outputs/models/selected_model.joblib`. About 4–5 minutes. Deterministic given seed 42. |
| Quick smoke run of modelling | `.venv/Scripts/python -m src.modelling.run_modelling --sample 0.05` | Writes to `outputs/model_metrics/smoke/` (git-ignored); no figures or model file |
| Rebuild model figures only | `.venv/Scripts/python -m src.reporting.model_figures` | Figures 10–14 from saved outputs |
| Tests | `.venv/Scripts/python -m pytest -q` | All pass (see TESTING.md) |

Exit codes: `0` success; `1` snapshot not found; `2` ingestion failure or a blocking validation gate failed (the previous outputs are left untouched).

## Why your numbers may differ from the README

The source is updated daily, and the pipeline always downloads the **current** published data (DEC-003, DEC-004). Results quoted in the docs come from snapshot `20261012T010041Z`:

- 242,454 rows
- SHA-256 `32b767d68e9f22b2e48a95a942d233cb13b311f1d06633e456743020c47fecdf`

A later snapshot will contain more months, and its counts will differ. Your snapshot's `manifest.json` and `outputs/data_quality/dq_report.md` record exactly what you processed.

The analysis is deterministic for a given snapshot. The only randomness is the H5 bootstrap, which uses seed 42 from config.

| Build Power BI tables | `.venv/Scripts/python -m src.reporting.build_bi_tables` | `data/curated/*.csv` (SQL star schema cross-checked against pandas; profiles; DAX expected values). About 20 s. |
| Generate the Power BI project | `.venv/Scripts/python -m src.reporting.build_pbip` (committed version, placeholder path) or `... build_pbip --local-path` (to open locally) | `powerbi/HDB Resale Market.pbip` + `.SemanticModel` + `.Report`. See BI_BUILD_GUIDE §2 and DEC-029. |
| Validate TMDL offline (Windows + Power BI Desktop) | `powershell -ExecutionPolicy Bypass -File powerbi/tools/validate_tmdl.ps1` | `TMDL OK: ...` |
| Validate DAX in Desktop (after opening and refreshing) | `powershell -ExecutionPolicy Bypass -File powerbi/tools/query_model.ps1` | `ALL CHECKS PASSED`; writes `data/curated/dax_validation_results.csv` |

**Run order:** `src.pipeline` → `src.analytics.run_analysis` → `src.modelling.run_modelling` → `src.reporting.build_bi_tables` → `src.reporting.build_pbip` → open the `.pbip` in Power BI Desktop and click Refresh. See BI_BUILD_GUIDE §2.

## Verified clean-room reproduction (Phase 5, 2026-10-12)

| Step | What was done | Result |
|---|---|---|
| 1. Fresh clone | `git clone` of commit `0829184` into an empty folder outside the project | OK |
| 2. Fresh environment | New venv, `pip install -r requirements.txt` | Installed, but resolved **`wrapt 2.5.1rc1`** (a pre-release transitive dependency) instead of the tested 2.5.0. This is why the lock file is now the documented install path. |
| 3. Exact environment | `pip install -r requirements-lock.txt` | `pip freeze` **identical** to the lock file |
| 4. Same raw snapshot | Copied `data/raw/20261012T010041Z/`, ran `src.pipeline --skip-download` → `run_analysis` → `run_modelling` → `build_bi_tables` → `build_pbip`, then `pytest` | All 5 steps exit 0. **113 tests passed** (the suite at that commit). |
| 5. Byte-level comparison | `git add -A && git diff --cached --stat` in the clone (content compared after line-ending normalisation) | Only timing fields differed: `runtime_seconds` in `model_results.json` and `fit_seconds` in `validation_scores.csv`. **Every data table, metric, hypothesis result, curated table and Power BI file was identical.** |
| 6. Figures | Figures 10 and 11 differed by 4 and 97 pixels | Cause: the committed versions were drawn from the saved CSVs (6 significant figures), while the run drew from full-precision memory. Redrawn from the same CSVs, they were **identical**. Fixed: `run_modelling` now always draws from the saved outputs. |
| 7. Live refresh | `python -m src.pipeline` (fresh download) in the clone | New snapshot `20261012T124241Z` was created next to the earlier one, which stayed untouched. The row-count gate compared it with the previous snapshot and passed. SHA-256 was identical to the morning download (the source had not been republished since 02:10 SGT), so a refresh *with new rows* could not be observed live; unit tests cover that path. |

**Conclusion:** for the same raw snapshot, the documented commands reproduce every committed output exactly, apart from wall-clock timings.
