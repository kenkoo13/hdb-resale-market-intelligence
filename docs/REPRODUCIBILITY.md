# Reproducibility

## Environment

| Item | Tested with |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| Python | 3.14.4 |
| Dependencies | `requirements.txt` (direct, pinned); `requirements-lock.txt` (full freeze) |
| Network | Required only to download the source data. No API key is needed. |
| Random seed | 42 (`config/project_config.example.yaml`; used from Phase 3) |

## Setup

```bash
git clone https://github.com/kenkoo13/hdb-resale-market-intelligence.git
cd hdb-resale-market-intelligence
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
# .venv/bin/python -m pip install -r requirements.txt       # macOS / Linux
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
| Generate the Power BI project | `.venv/Scripts/python -m src.reporting.build_pbip` | `powerbi/HDB Resale Market.pbip` + `.SemanticModel` + `.Report`, with `CuratedFolder` set to this machine's path |
| Validate TMDL offline (Windows + Power BI Desktop) | `powershell -ExecutionPolicy Bypass -File powerbi/tools/validate_tmdl.ps1` | `TMDL OK: ...` |
| Validate DAX in Desktop (after opening and refreshing) | `powershell -ExecutionPolicy Bypass -File powerbi/tools/query_model.ps1` | `ALL CHECKS PASSED`; writes `data/curated/dax_validation_results.csv` |

**Run order:** `src.pipeline` → `src.analytics.run_analysis` → `src.modelling.run_modelling` → `src.reporting.build_bi_tables` → `src.reporting.build_pbip` → open the `.pbip` in Power BI Desktop and click Refresh. See BI_BUILD_GUIDE §2.
