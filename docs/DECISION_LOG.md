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
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted (confirmed by the repository owner on 2026-10-12)
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
- **Phase 1 evidence (2026-10-12 snapshot):** 2026-10 has 750 rows. 2026-09 has 2,245 rows, which is within the range of the preceding months, so there is no evidence yet that the prior month is incomplete. With only one snapshot, late-registration behaviour cannot be measured. Comparing month counts across future snapshots will settle this, so the status stays Provisional.

### DEC-009 — Exact-duplicate rows are retained and flagged, not deleted
- **Date / Owner / Status:** 2026-10-12 / Project / **Superseded by DEC-013**. The Phase 1 investigation found a specific artefact pattern. The general principle of keeping duplicates still holds.
- **Decision:** Rows identical on all 11 source fields are retained. They get a `duplicate_group_size` flag, and a sensitivity check compares key metrics with and without duplicates.
- **Reason:** There is no transaction ID. Two sales of physically similar units (same block, same three-storey band, same model and area) in the same month at the same round-number price are plausible, so deletion could remove real transactions.
- **Alternatives:** Drop exact duplicates (common, but unsupported by evidence); drop duplicates on a reduced key (would remove even more genuine sales).
- **Trade-offs:** If some duplicates are actually double publication, counts are overstated by at most about 0.13% (318 / 242,454).
- **Validation:** Phase 1 profiles duplicate groups (block or flat-type concentration, price roundness) and reports the sensitivity results.
- **Revision criteria:** The publisher confirms that duplicates are errors, or the profiling shows patterns typical of a system duplication.

### DEC-010 — Read every field as text; quarantine only uninterpretable core fields
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** The raw CSV is read with `dtype=str, keep_default_na=False`, so nothing is coerced or turned into a missing value when the file is read. Strict regex parsers (`src/transformation/parsers.py`) then convert each field.
  - A row is **quarantined** when a *core* field is blank or unparseable, or the month is outside coverage. The core fields are month, town, flat_type, storey_range, floor_area_sqm and resale_price. Quarantined rows move to `data/processed/quarantine.csv` with their original text and reason codes.
  - A problem in a *secondary* field (block, street_name, flat_model, lease fields) only nulls that field and sets a `flag_*` column. The row is kept.
- **Reason:** pandas' default missing-value inference would silently turn strings such as `"NA"` into missing values and hide format changes. Quarantining a whole row for a secondary-field issue would throw away a valid price observation.
- **Alternatives:** `pd.to_numeric(errors="coerce")` (accepts `1e5`, `inf` and similar); dropping every row with any issue.
- **Evidence:** No core-field failures in the 2026-10-12 snapshot (0 rows under Q01–Q06). The rules are exercised by the synthetic-fixture tests.
- **Trade-offs:** The strict parsers would reject a legitimate future format change, such as thousands separators. This is intentional: the change shows up as quarantined rows in the DQ report, and the parser is then extended deliberately.
- **Validation:** `tests/test_parsers.py`, `tests/test_clean.py`.
- **Revision criteria:** The publisher changes a field format.

### DEC-011 — Plausibility bounds flag rows but never delete them
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** A floor area outside 20–400 sqm or a price outside SGD 50,000–3,000,000 sets `flag_implausible_*`. The row is kept.
- **Reason:** The bounds catch unit or scale errors (for example, price in thousands or area in sq ft) without judging legitimately unusual flats. The observed ranges (area 31–366.7 sqm, price SGD 140,000–1,728,000) sit well inside them, so 0 rows are flagged.
- **Alternatives:** IQR or z-score outlier removal. Rejected because it would remove genuinely large flats and high-value sales, which are segments users want to understand.
- **Trade-offs:** The bounds are a judgement call and deliberately wide, so subtle errors inside them are not caught.
- **Validation:** Fixture row 17 (15 sqm) is flagged and kept.
- **Revision criteria:** The flagged count becomes non-zero. Investigate before changing the bounds.

### DEC-012 — Remaining lease: use the source value; the derived value is only a consistency check
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** `remaining_lease` is parsed into months and years and used as the lease variable. A derived value is computed only to check consistency:

  `99 − (transaction year − lease_commence_year + (month − 1) / 12)`

  A row where the source and derived values differ by more than 1.5 years gets `flag_lease_inconsistent`.
- **Reason:** The source value is recorded by HDB. The derived value has to assume the lease started on 1 January, because only the year is published, so it can understate the remaining lease by up to about one year. The 1.5-year tolerance covers that ambiguity plus month rounding.
- **Evidence:** Source minus derived has a median of 0.50 years, a 1st–99th percentile range of 0.00 to 1.00, and a maximum of 1.5. That is the expected 0–1 year bias. Exactly one row exceeds the tolerance:
  - JURONG EAST blk 37 TEBAN GDNS RD, 2025-01, lease_commence_date 1981, remaining lease 40y01m.
  - The other 11 rows for that block record 1966, and 40y01m is consistent with 1966. The 1981 value is therefore probably a data-entry inconsistency in the source.
  - The row is **flagged, not corrected**, because the project does not edit source values.
- **Alternatives:** Derive the remaining lease for every row (less accurate); correct the outlier from the block's other rows (rejected because it edits source data on inference).
- **Trade-offs:** The source uses three formats (`N years`, `N years N month`, `N years N months`), and the parser handles all three.
- **Validation:** `tests/test_parsers.py` (format coverage), `tests/test_clean.py::test_lease_inconsistency_flagged`.
- **Revision criteria:** A new format appears, or the discrepancy distribution shifts.

### DEC-013 — Suspected 2017 duplicate-publication artefact moved to the exception report (supersedes DEC-009)
- **Date / Owner / Status:** 2026-10-12 / Project / Provisional. The internal evidence is strong, but the publisher has not confirmed it.
- **Decision:** Exact-duplicate groups are rows identical on all 11 source fields. For these groups, every copy after the first (by source row order) moves to the exception report with reason `Q07_suspected_duplicate_artefact`, **but only if** the row was registered in 2017 **and** priced at exactly SGD 468,000 or 470,000. All other exact duplicates are kept and annotated with `duplicate_group_size`.
- **Reason (2026-10-12 snapshot):**
  - Duplicate rows concentrate in 2017: 344 of 635. The 2017 duplicate rate is 1.68%, against 0.08–0.21% in every later year.
  - Of those 344, 294 are priced at exactly 468,000 or 470,000. No later year has a duplicate row at either price.
  - The second copy usually sits out of position, after the highest-priced row in its month/town/flat-type run, not next to its twin.
  - Removing the 147 excess copies leaves 232 rows at those two prices in 2017. That is close to 2018's 220, whereas keeping them gives an anomalous 379.
  - Genuine twin sales would not cluster at two specific prices in a single year.
- **Alternatives:**
  - Keep all duplicates (DEC-009). Rejected given the evidence above.
  - Drop all exact duplicates. Rejected because the remaining duplicates fit genuine near-identical sales in the same block, storey band and month. They run at about 0.1% a year, mostly sit on adjacent rows, and are mostly 4-ROOM.
  - Ask HDB. This is outside the project's control, so it is recorded as an open question.
- **Impact (sensitivity check):**
  - 147 rows removed, 0.06% of the snapshot.
  - The 2017 median (SGD 410,000) and the overall median (SGD 505,000) are unchanged.
  - Five 2017 monthly medians move by at most SGD 5,000. The largest monthly count change is 16 rows.
- **Trade-offs:** The rule targets one observed pattern. If HDB fixes the source, the rule simply matches nothing.
- **Validation:** `tests/test_clean.py::test_2017_artefact_keeps_first_copy` and `test_genuine_duplicate_kept_and_annotated`. Deliberately changing the rule's year made 7 tests fail.
- **Revision criteria:** The publisher confirms or refutes the duplication, or the pattern changes in a future snapshot (check `Q07` in the DQ report).

### DEC-014 — Snapshot retention is manual
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** The pipeline never deletes raw snapshots, and old ones in `data/raw/` can be removed by hand. The row-count gate compares only against the most recent snapshot older than the one being processed.
- **Reason:** Automatic deletion of data is risky and not needed. Each snapshot is about 24 MB.
- **Revision criteria:** Disk usage becomes a problem.

### DEC-015 — Medians as headline statistics; 24-month recent window for current comparisons
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Headline prices are medians with 25th–75th percentiles, always shown with transaction counts. Comparisons of the "current market" use the 24 full months ending at the last full month (pre-registered in HYPOTHESIS_REGISTER §1). Segments with fewer than 30 sales are labelled `low_sample`.
- **Reason:** Prices are right-skewed. Measured skewness is 0.98 for the full period and 0.92 for the recent window, and the mean exceeds the median by SGD 27k–31k, so the mean overstates a typical transaction. A 24-month window balances recency, because prices rose about 58% for comparable flats since 2017, against sample size: 50,902 rows, and every town has at least 35 4-ROOM sales.
- **Alternatives:** Means (sensitive to the expensive tail); a 12-month window (more current, but thinner cells; 1-ROOM would have fewer than 10 sales); the whole period (mixes very different price levels).
- **Trade-offs:** A 24-month median still contains some price drift: the mix-adjusted index rose about 4% from 2024-10 (151.6) to 2026-09 (157.5). Within-window comparisons are of segments, not points in time, and the hedonic models absorb the drift with month fixed effects.
- **Validation:** `tests/test_analytics.py::test_segment_summary_values_and_low_sample_flag`.
- **Revision criteria:** The market moves fast enough that 24 months straddles materially different regimes. In that case shorten the window.

### DEC-016 — Hedonic regression with month fixed effects and building-clustered errors (M1/M2)
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Use log-price OLS with month, town, flat type and flat model fixed effects plus floor area, storey midpoint and remaining lease (M1). M2 replaces storey and lease with bands. Standard errors are clustered by building (block + street).
  - The known rank deficiency (flat type MULTI-GENERATION ≡ flat model "Multi Generation") is left in place. It does not affect the tested terms, which were verified to be uniquely estimable by a rank check. The aliased level is marked `separately_identified = False` in the flat-model effects table.
- **Reason:** This is the standard, interpretable way to compare like-for-like properties. Log price gives percentage effects. Clustering reflects that sales in the same building share unobserved location and quality.
- **Alternatives:**
  - Separate models per flat type: fewer assumptions, but more estimates and smaller samples.
  - Mixed models with building random effects: more complex and harder to explain.
  - Dropping flat model to remove the aliasing: rejected because it would change the pre-registered specification.
- **Evidence:** Synthetic tests recover known coefficients inside their CIs (`test_hedonic_recovers_known_coefficients`). On the real data, results are stable across 4 specifications.
- **Trade-offs:** Effects are averages across towns and types. Interactions (for example, whether the storey premium differs by town) are not modelled.
- **Revision criteria:** Evidence of strong effect heterogeneity is needed for the BI audience, in which case add interactions as an exploratory extension.

### DEC-017 — Mix-adjusted price change measured with a hedonic time-dummy index
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Mix-adjusted price change = the change in the mean of exp(month coefficients) from M1 fitted on the full period, with 2017 = 100. It is published monthly as `price_index_monthly.csv`, alongside the raw median index.
- **Reason:** It separates "prices of comparable flats changed" from "a different mix of flats was sold". This is the core requirement of brief §7.
- **Alternatives:**
  - Stratified median (a fixed-weight average of cell medians): simpler, but thin cells make it noisy, and it only controls for the stratifying variables.
  - Repeat-sales index: not possible, because there is no unit identifier.
- **Trade-offs:** It assumes constant characteristic premiums over time. Month coefficients for low-volume months (2020-04 and 2020-05) are less precise.
- **Validation:** `test_month_index_recovers_market_trend`, `test_period_change_matches_definition_and_truth`.
- **Revision criteria:** Premiums shift substantially over time. In that case use a chained or rolling-window index.

### DEC-018 — Static figure design conventions
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Figures are matplotlib PNGs that follow these conventions:
  - a validated categorical palette, with no more than 3 coloured series and direct labels;
  - one y-axis per chart, so raw and adjusted values go in separate panels;
  - titles phrased as the question answered, subtitles giving population, period and n;
  - a source and licence note on every figure;
  - the partial month drawn hatched, never as a normal bar.
- **Reason:** Readability for a business audience and honest presentation (brief §4.3). The licence requires attribution.
- **Validation:** Each figure was rendered and inspected, which caught and fixed three label collisions.
- **Revision criteria:** None expected.

### DEC-019 — Chronological 12/12-month validation and test blocks; static and monthly-refit evaluation
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted (pre-specified in MODEL_CARD §3, commit `dc67c89`)
- **Decision:** Train on 2017-01 to L−24, validate on the next 12 months, and test on the last 12 full months. The test year is evaluated twice: *static* (trained once, predicting 1–12 months ahead) and *monthly refit* (retrained before each test month). Selection uses validation only.
- **Reason:** Prices trend strongly (Phase 2: +57% for comparable flats since 2017), so random splits would let the model "see the future" and overstate accuracy. Two modes show both decay with horizon and deployment-realistic accuracy.
- **Alternatives:** A random K-fold split (rejected: leaks the time trend); a single expanding-window backtest across many years (more evidence, but higher cost and complexity; the monthly refit over 12 test months covers the deployment question).
- **Trade-offs:** The test covers one year (2025-10 to 2026-09), so performance in a different market regime may differ.
- **Validation:** `tests/test_modelling.py::test_split_is_chronological_and_disjoint`.
- **Revision criteria:** The market regime changes sharply. In that case add multi-year rolling backtests.

### DEC-020 — Ridge time-spline extrapolation chosen on validation
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted (added before training, commit `0ff236e`)
- **Decision:** The Ridge grid includes `time_extrapolation` ∈ {constant, linear}.
- **Reason:** Validation and test months lie beyond the training period, so the model must decide what happens after the last training month. Neither option is obviously right.
- **Evidence (synthetic check, not real data):** with a truly linear synthetic trend, `linear` extrapolation still produced about 2× the MAE of `constant` at a 1–12-month horizon. The spline's end slope is estimated from few, noisy months. This is a caution, and validation decides on the real data.
- **Revision criteria:** The validation results.

### DEC-021 — Additional baseline B2 (segment median over the last 12 months), added after the smoke run
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Add B2, the town × flat-type median over the last 12 training months (with the same fallbacks as B1), to all comparisons and to the monthly-refit evaluation. B0 and B1 remain as pre-specified.
- **Reason:** The 5% smoke run showed that B1, the median over *all* training years, predicts years-old price levels into the test period. Beating it says little. B2 is the realistic comparator: "what similar flats in this town sold for in the past year".
- **Transparency:** B2 was added *after* seeing smoke-run output on a 5% sample, which included test months. It is a comparator only and is never eligible for selection, so it cannot bias model choice. No other design element was changed after the smoke run, including the selection rule, grids, interval method and metrics.
- **Validation:** `test_segment_baseline_fallbacks_and_recent_window`.

### DEC-022 — Log-price target with exp back-transform; MAE primary
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted (pre-specified MODEL_CARD §2, §6)
- **Decision:** Models fit `log(price)`. Predictions are `exp(prediction)`, an estimate of the conditional median. The primary metric is MAE in SGD, with RMSE, R², MedAE and MdAPE also reported.
- **Reason:** Price errors scale with price level, and logs stabilise this. The median-type back-transform pairs naturally with MAE. MAE is directly interpretable as dollars of typical error and is robust to rare extreme prices.
- **Alternatives:** Raw-price target with squared error (dominated by expensive flats); a smearing correction to estimate the mean (unnecessary for an MAE objective).
- **Trade-offs:** Predictions are slightly below the conditional mean, so mean signed error can be negative even when median bias is about zero.

### DEC-023 — Prediction intervals withheld from the BI layer
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted (applies the rule pre-specified in MODEL_CARD §6)
- **Decision:** Do not publish the 80% split-conformal intervals. Show the empirical test error distribution and segment MdAPE instead.
- **Evidence:** Test coverage was 64.9% static and 70.9% monthly refit, against the nominal 80%. Static coverage decays from 74% to 58% over 12 months, because validation residuals (a rising market) differ from test residuals (a flat market).
- **Alternatives:** Publish with a warning (rejected: users would read an interval as a guarantee); recalibrate on test (rejected: that uses test data to tune); an adaptive or rolling conformal method (a future option, which would need its own validation).
- **Revision criteria:** An interval method shows ≥ 78% coverage in a held-out backtest across more than one market regime.

### DEC-024 — Selected model: gradient boosting with street target encoding (G-B)
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Use HistGradientBoosting on log price with feature set A plus street target encoding (31 leaves, min leaf 20, learning rate 0.1, up to 1,000 iterations, seed 42). It is evaluated both trained once and retrained monthly, and monthly retraining is recommended for any use.
- **Reason:**
  - Lowest validation MAE (28,958), more than 1% better than any simpler family. The next best simpler family, G-A, was 30,904.
  - Confirmed on the test year: static MAE 27,578, monthly refit 25,387, against the realistic baseline B2 at 84,509.
- **Alternatives:**
  - Ridge (L-B): more interpretable, but 60% higher MAE.
  - Larger grids or other libraries (LightGBM, XGBoost): extra dependencies and complexity for an uncertain gain, not justified for this project's purpose.
- **Trade-offs:** Less transparent than a linear model. Explanation relies on permutation importance and segment errors, plus the Phase 2 hedonic model for interpretable effects. The model cannot extrapolate time trends.
- **Validation:** MODEL_CARD §7, `tests/test_modelling.py`.
- **Revision criteria:** Monthly-refit MAE on new data rises materially above about 28k, or a simpler model comes within 1% on validation.

### DEC-025 — Power BI delivered as a generated PBIP (TMDL + PBIR) validated against Desktop's own engine
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Generate a Power BI Project from Python (`src/reporting/build_pbip.py`) instead of hand-building a `.pbix`. Validate it in three ways:
  - Power BI's own TMDL serializer;
  - opening it in Power BI Desktop 2.158 and refreshing through its local engine;
  - DAX queries over ADOMD.NET compared with Python expected values.
- **Reason:** A `.pbix` is a binary that cannot be produced reliably by code, and faking one is prohibited by the brief. PBIP is Microsoft's text format for source control, so the model and report become reviewable, diffable and reproducible.
- **Alternatives:** Hand-build in Desktop (not reproducible; manual drift); a manual build guide only (the fallback; less useful); third-party PBIX generators (unofficial).
- **Evidence:** TMDL parse OK; the project opened; refresh succeeded; 13/13 DAX values, 37/37 measures and 17/17 row counts passed (BI_BUILD_GUIDE §1).
- **Trade-offs:**
  - Visual rendering cannot be machine-verified and needs a person to review it (BI_BUILD_GUIDE §8).
  - Report JSON follows published schemas, but a future Desktop version may upgrade or reject older schema versions.
  - The CSV folder path is an absolute Power Query parameter.
- **Revision criteria:** Desktop rejects the format, in which case use the manual fallback in BI_BUILD_GUIDE §10.

### DEC-026 — Indicative estimates as pre-computed typical profiles, not live inference
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** Page 5 shows 288 pre-computed estimates: 96 town × flat-type segments, each with at least 30 sales in the latest 12 months, × 3 storey levels. Profile attributes are segment medians or modes. Each estimate carries a typical error (the larger of the town and flat-type monthly-refit MdAPE), a reliability label and the segment's actual median.
- **Reason:** Power BI Desktop (free) cannot run the Python model on slicer changes. The brief forbids implying live inference.
- **Alternatives:** Python visuals in Power BI (would need a Python runtime in Desktop and still not use the trained model reproducibly); exporting the model to ONNX or DAX (impractical for gradient boosting); omitting the page (loses a useful, honest illustration).
- **Evidence:** Profile estimates vs segment medians: median −0.2%; low / middle / high storey −5.2% / +0.5% / +3.9%. The extremes (+31% to +34%, Central Area 4-ROOM with a premium modal model) are labelled less reliable.
- **Trade-offs:** The profiles are typical flats, not the user's flat. Modal attributes can be unrepresentative in mixed segments.
- **Revision criteria:** A supported way to run inference in the free tier appears, or users need custom profiles. In that case, publish a small Python CLI instead.

### DEC-027 — Explicit DAX measures only; windows from SQL-computed month flags
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:**
  - Every column has `summarizeBy: none`, and all numbers in visuals come from 37 named, documented measures.
  - The "latest 12 months" and "prior 12 months" windows are flags in `dim_month`, computed in SQL relative to the last *full* month. Auto date/time is disabled.
- **Reason:**
  - Implicit sums of prices would be meaningless.
  - Time-intelligence functions relative to the last date would include the partial month (DEC-008).
  - Flags keep one definition of each window across Python, SQL and DAX.
- **Validation:** The DAX values for the latest-12 and prior-12 medians, YoY, P25/P75 and counts equal the Python values exactly.
- **Revision criteria:** None expected.

### DEC-028 — SQL (SQLite) builds the star schema and independently cross-checks pandas
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:** `sql/01_fact_and_dimensions.sql` builds the fact and dimension tables. `sql/02_aggregates.sql` computes monthly and town × type medians with window functions. `build_bi_tables` aborts unless they equal the pandas results exactly (absolute tolerance 1e-6 SGD).
- **Reason:** It demonstrates SQL proficiency, and an independent implementation catches logic errors.
- **Evidence:** 118 monthly rows and 127 town × type cells match. A unit test showed that the original `np.allclose` default tolerance (relative 1e-5) let a SGD 1 tamper pass; the tolerance was tightened.
- **Trade-offs:** SQLite has no `MEDIAN()`, so the median is implemented with a documented `ROW_NUMBER` pattern. SQL band edges must stay in sync with Python, which a test enforces.

### DEC-029 — Placeholder data-folder path in the committed Power BI project
- **Date / Owner / Status:** 2026-10-12 / Repository owner / Accepted
- **Decision:** The committed PBIP sets `CuratedFolder` to `C:\path\to\hdb-resale-market-intelligence\data\curated\`. Local validation uses `build_pbip --local-path`. A test (`test_generated_pbip_has_no_personal_path`) fails while a personal path is present, which acts as a guard before committing.
- **Reason:** Power Query needs an absolute path, but committing this machine's path would expose a personal Windows folder name on a public repository.
- **Trade-offs:** Each user sets the parameter once (BI_BUILD_GUIDE §2), or regenerates with `--local-path`.

### DEC-030 — Plain business language for every dashboard label
- **Date / Owner / Status:** 2026-10-12 / Repository owner / Accepted
- **Decision:**
  - All report text is rewritten for non-technical managers: page names, headers, KPI and chart titles, table headers, legends, filters, data values shown in visuals and notes.
  - Every plain term is defined once in `docs/DASHBOARD_GLOSSARY.md`, mapped to its technical term.
  - Plain-language label columns are generated from the same data (for example, "10 floors higher: about 7.8% more" is built from the H1 estimate), so they stay correct after a refresh.
  - Calculations, DAX measure definitions, data and model logic are unchanged.
- **Reason:** The report's audience is business owners. Statistical and modelling terms (MAE, P25, confidence interval, ε², hypothesis IDs, "gradient boosting") were barriers to using the findings.
- **Terminology choice:** MAE is shown as **"Average prediction error"**, not "typical", because it is a mean. MdAPE is shown as **"Typical error (%)"** (a median). This keeps the labels accurate and the two KPIs distinct. See the glossary, §3.
- **Validation:** The DAX checks (13 values, 37 measures, 17 row counts) were re-run after the change, and every visual field reference was tested. The text-length fit was confirmed with screenshots of the real report.
- **Revision criteria:** User feedback shows a term is still unclear.

### DEC-031 — Exact reproduction installs from the lock file; documentation figures are tested
- **Date / Owner / Status:** 2026-10-12 / Project / Accepted
- **Decision:**
  - The documented install command is `pip install -r requirements-lock.txt`. `requirements.txt` remains the list of direct dependencies.
  - Key figures quoted in the README and docs are checked against the outputs by `tests/test_docs_consistency.py`.
  - The DAX catalogue in BI_BUILD_GUIDE is checked against the code.
- **Reason:** The Phase 5 clean-room install from `requirements.txt` resolved a pre-release transitive dependency (`wrapt 2.5.1rc1`). The documentation audit found the DAX catalogue stale after the Phase 4 wording change. Both are drift risks that tests can catch automatically.
- **Trade-offs:** After a refresh to a newer snapshot, the documentation tests skip (with a reason) until the narrative is reviewed and `DOCUMENTED_SNAPSHOT` is updated.
- **Validation:** The lock install gave a `pip freeze` identical to the lock. Mutation check: changing two README figures caused 2 failures.
