# Decision Log

Material decisions that affect data integrity, analytical validity, model performance, interpretability, or user understanding.
Decisions are never deleted. A changed decision gets a new ID and marks the old one `Superseded by DEC-xxx`.

Status values: `Accepted`, `Provisional` (evidence incomplete), and `Superseded`.
Owner: "Project" unless stated otherwise.

---

### DEC-001 — Sole transaction source
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Use only data.gov.sg dataset `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` ("Resale flat prices based on registration date from Jan-2017 onwards", published by HDB).
- **Reason:** This is a project constraint. A single official source also keeps lineage unambiguous.
- **Alternatives:** (a) Append the 2012–2014 and 2015–2016 datasets for a longer series. Rejected because the brief forbids it, and earlier datasets lack `remaining_lease`, so the schema would be inconsistent. (b) Enrich with geocoding or amenities. Rejected as an unapproved external source.
- **Evidence:** Live metadata (see PROJECT_PLAN §2.2).
- **Trade-offs:** About 9.75 years of history. There are no location coordinates, so location is captured only through town, street, and block.
- **Validation:** Ingestion is hard-wired to the configured dataset ID. A test asserts the manifest records that ID.
- **Revision criteria:** HDB retires or renames the dataset. In that case report it and stop; do not substitute a source.

### DEC-002 — Ingestion mechanism: full-snapshot bulk CSV via the data.gov.sg download API
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Call `initiate-download` then `poll-download` (v1 open API), and download the full CSV from the returned signed URL. The paginated `datastore_search` API is a documented fallback only. It is not used automatically.
- **Reason:** One request returns a consistent full snapshot (about 24 MB) of the published table. Paging about 242k rows through `datastore_search` would take many requests and risks an inconsistent read if the table updates mid-pagination.
- **Alternatives:** `datastore_search` pagination; manual browser download.
- **Evidence:** Both endpoints were exercised on 2026-10-12. The bulk CSV had 242,454 data rows, which equals the datastore `total`.
- **Trade-offs:** It depends on a two-step API and an expiring signed URL. Every refresh re-downloads 24 MB.
- **Validation:** Unit tests with mocked HTTP responses cover success, poll timeout, HTTP errors, and malformed responses.
- **Revision criteria:** data.gov.sg deprecates the endpoint, or the dataset grows enough that full download becomes impractical.

### DEC-003 — Refresh strategy: full replacement snapshot, not incremental append
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Each refresh downloads the full dataset into a new immutable snapshot folder, `data/raw/<UTC timestamp>/`. Downstream tables are rebuilt from that snapshot. Nothing is ever appended to a previous output.
- **Reason:** The source has no transaction ID or change feed, so incremental merges could not reliably detect changed or removed rows. Appending would also risk accidental duplicates. Full rebuilds make the output a pure function of one snapshot.
- **Alternatives:** Incremental retrieval by month (rejected: late registrations and corrections would be missed); a hash-based upsert (rejected: no natural key).
- **Evidence:** Exact-duplicate rows exist (318 in the 2026-10-12 snapshot), which shows that row content cannot serve as a key.
- **Trade-offs:** More download volume. Row-level differences between snapshots are not tracked, only snapshot-level counts and month coverage are compared.
- **Validation:** A test checks that rerunning transformation on the same snapshot gives identical outputs (idempotency). The manifest records row count and SHA-256 hash.
- **Revision criteria:** HDB adds a stable transaction identifier.

### DEC-004 — Raw data is not committed to Git
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** `data/raw` and `data/processed` are git-ignored. The data is obtained at runtime with `python -m src.pipeline`. Unit tests use small synthetic fixtures that are clearly labelled. Small aggregated curated tables may be committed so the repository can be browsed without running the pipeline (decided per table in Phase 4).
- **Reason:** The source is updated daily and is about 24 MB. Committing it would bloat history and quickly become stale. Reproducibility comes from the documented download plus the manifest hash.
- **Alternatives:** Commit the raw CSV (rejected); Git LFS (unnecessary complexity).
- **Trade-offs:** Someone reproducing the project later gets a newer snapshot, so their numbers may differ slightly from the published README. The README states the snapshot date and hash.
- **Validation:** Review `.gitignore` and check `git status` before committing.
- **Revision criteria:** An exact historical reproduction is required. In that case, archive one snapshot as a release asset.

### DEC-005 — Language, storage, and tooling
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Python 3.14 with pinned dependencies (pandas, scikit-learn, scipy, statsmodels, matplotlib, pyarrow, requests, PyYAML, pytest). Parquet is the processed format. SQLite (Python standard library) holds the SQL layer for curated aggregates and cross-checks. CSV is the Power BI import format.
- **Reason:** These libraries are widely understood by reviewers. SQLite needs no server and is in the standard library. Power BI Desktop imports CSV natively, while SQLite would need a third-party ODBC driver on the user's machine.
- **Alternatives:** DuckDB (excellent, but an extra dependency and less familiar to BI reviewers); PostgreSQL (needs a server, so it is overkill); Power BI reading Parquet (supported, but CSV is simpler to inspect in GitHub).
- **Evidence:** A dry-run install confirmed Python 3.14 wheels exist for all pinned packages.
- **Trade-offs:** Python 3.14 is recent, so reviewers on older Python may need 3.11+ (to be tested in Phase 5). SQL logic in SQLite has fewer analytic functions (for example, there is no native median), and this is documented where relevant.
- **Validation:** Installation in a fresh `.venv`. Tests run under that environment.
- **Revision criteria:** A dependency fails to install for reviewers.

### DEC-006 — Failed refresh must not corrupt last valid outputs
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Every stage writes to a temporary path and atomically replaces the target only after its validation gate passes. Blocking validation failures (schema change, zero rows, row count dropping by more than the configured threshold against the previous manifest) stop the pipeline with a non-zero exit code and leave the previous processed and curated outputs untouched.
- **Reason:** The project brief requires it, and it prevents silent corruption of BI inputs.
- **Alternatives:** Overwrite in place (rejected).
- **Validation:** A unit test simulates a schema-changed snapshot and asserts that the previous output files are unchanged.
- **Revision criteria:** None expected.

### DEC-007 — Code licence MIT; data under Singapore Open Data Licence v1.0
- **Date / Owner / Status:** 2026-10-12 / Project / Provisional (the repository owner may prefer a different code licence)
- **Decision:** Project source code is under the MIT License. Source data and derived data remain under the Singapore Open Data Licence v1.0, with attribution recorded in `DATA_LICENSE.md` and the README. A no-endorsement statement is included.
- **Reason:** MIT is permissive and standard for portfolio code. The data licence is fixed by the publisher and requires a conspicuous attribution with a licence link. It also forbids implying official status.
- **Alternatives:** Apache-2.0 (patent clause unnecessary here); no licence (would make the code legally "all rights reserved", which is unhelpful for a public portfolio).
- **Validation:** The licence text was read from data.gov.sg on 2026-10-12.
- **Revision criteria:** The repository owner selects another licence.

### DEC-008 — Incomplete current month is flagged and excluded from trends and model evaluation
- **Date / Owner / Status:** 2026-10-12 / Project / Provisional (the rule will be confirmed against Phase 1 profiling)
- **Decision:** A month on or after the snapshot's retrieval month (Singapore time) is flagged `is_partial_month = True`. It stays in the clean data, but it is excluded from monthly trend statistics, hypothesis tests, and model training and evaluation. Power BI shows it as provisional.
- **Reason:** The dataset is by *registration* date, so the current month is still being populated. 2026-10 had 750 rows on 2026-10-12, against about 2,100–2,650 in recent full months. Including it would show a false volume collapse.
- **Alternatives:** Drop the rows entirely (loses data for no reason); use a volume-based heuristic (fragile).
- **Trade-offs:** The latest few weeks of data are not used for trend conclusions.
- **Validation:** Unit test on a synthetic snapshot date. Phase 1 reports the counts.
- **Revision criteria:** Evidence shows late registrations keep arriving for earlier months. In that case, extend the rule to the prior month.

### DEC-009 — Exact-duplicate rows are retained and flagged, not deleted
- **Date / Owner / Status:** 2026-10-12 / Project / Provisional (pending the Phase 1 investigation)
- **Decision:** Rows identical on all 11 source fields are retained. They get a `duplicate_group_size` flag, and a sensitivity check compares key metrics with and without duplicates.
- **Reason:** There is no transaction ID. Two sales of physically similar units (same block, same three-storey band, same model and area) in the same month at the same round-number price are plausible, so deletion could remove real transactions.
- **Alternatives:** Drop exact duplicates (common, but unsupported by evidence); drop duplicates on a reduced key (would remove even more genuine sales).
- **Trade-offs:** If some duplicates are actually double publication, counts are overstated by at most about 0.13% (318 / 242,454).
- **Validation:** Phase 1 profiles duplicate groups (block or flat-type concentration, price roundness) and reports the sensitivity results.
- **Revision criteria:** The publisher confirms that duplicates are errors, or the profiling shows patterns typical of a system duplication.
