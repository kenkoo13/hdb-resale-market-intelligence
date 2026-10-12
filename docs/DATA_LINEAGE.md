# Data Lineage

How the official source becomes each downstream artefact. Every artefact can be traced to exactly one raw snapshot through its `snapshot_id`.

```
[data.gov.sg] dataset d_8b84c4ee58e3cfc0ece0d773c8ca6abc  (HDB, updated daily)
   │  GET metadata → GET initiate-download → GET poll-download → GET signed CSV URL
   │  src/ingestion/datagov_client.py::create_snapshot
   ▼
data/raw/<snapshot_id>/resale_raw.csv          byte-identical copy, immutable, git-ignored
data/raw/<snapshot_id>/manifest.json           retrieval time, publisher metadata, rows, SHA-256
   │  src/pipeline.py::run_gates               BLOCKING: header contract, zero rows,
   │                                           row-count drop vs previous snapshot, CSV vs manifest rows
   │  src/transformation/clean.py::clean_snapshot
   │     R01–R03 normalise → parse (parsers.py) → Q01–Q07 quarantine → flags → derived fields
   ├──► data/processed/quarantine.csv          rows that cannot be safely used (original text + reasons)
   ├──► data/processed/transactions_clean.parquet   clean grain table (git-ignored)
   ├──► data/processed/run_info.json           snapshot id, counts, coverage
   └──► outputs/data_quality/dq_report.{json,md}    measured DQ results (committed)
```

| Stage | Input | Output | Code | Failure behaviour |
|---|---|---|---|---|
| Ingest | data.gov.sg API | `data/raw/<id>/` | `src/ingestion/datagov_client.py` | Retries transient errors, then raises `IngestionError`. A `.partial` folder is removed on failure, so no half-written snapshot is left. |
| Gate | raw CSV + manifest | pass/fail | `src/validation/schema.py`, `src/pipeline.py` | A blocking failure exits with code 2. Processed outputs are untouched. |
| Clean | raw CSV (text) | clean parquet, quarantine CSV | `src/transformation/clean.py` | Deterministic. Reprocessing the same snapshot gives identical output. |
| DQ report | raw + clean result | `outputs/data_quality/` | `src/validation/quality_report.py` | Written in the same atomic publish step as the processed files |

*Phases 2–4 extend this with analytical tables, model outputs and Power BI tables.*
