-- 01_fact_and_dimensions.sql
-- Builds the Power BI star schema from the cleaned transaction table.
-- Input : table `clean` (loaded by src/reporting/build_bi_tables.py from
--         data/processed/transactions_clean.parquet; Q01-Q07 rows already removed).
-- Output: fact_transactions, dim_month, dim_town, dim_flat_type, dim_storey_range, dim_flat_model.
-- Grain of fact_transactions: one registered resale transaction (incl. the partial month,
-- flagged via dim_month.is_partial_month so the report can show or exclude it).
-- Bands use the same edges as src/analytics/descriptive.py and hedonic.py (METRIC_DICTIONARY §2).

DROP TABLE IF EXISTS fact_transactions;
CREATE TABLE fact_transactions AS
SELECT
    source_row_number                          AS txn_id,
    month || '-01'                             AS month,
    town,
    flat_type,
    flat_model,
    storey_range,
    storey_mid,
    floor_area_sqm_num                         AS floor_area_sqm,
    CASE
        WHEN floor_area_sqm_num < 50  THEN '<50'
        WHEN floor_area_sqm_num < 70  THEN '50-69'
        WHEN floor_area_sqm_num < 90  THEN '70-89'
        WHEN floor_area_sqm_num < 110 THEN '90-109'
        WHEN floor_area_sqm_num < 130 THEN '110-129'
        WHEN floor_area_sqm_num < 150 THEN '130-149'
        ELSE '150+'
    END                                        AS floor_area_band,
    remaining_lease_years,
    -- 5-year lease band, e.g. 70-74 (floor(years/5)*5); zero-padded like the Python version.
    printf('%02d-%02d', CAST(remaining_lease_years / 5 AS INTEGER) * 5,
                        CAST(remaining_lease_years / 5 AS INTEGER) * 5 + 4) AS lease_band,
    lease_commence_year,
    resale_price_sgd                           AS resale_price,
    price_per_sqm_sgd                          AS price_per_sqm
FROM clean;

-- Month dimension: one row per month present; windows relative to the last FULL month (L).
DROP TABLE IF EXISTS dim_month;
CREATE TABLE dim_month AS
WITH months AS (
    SELECT DISTINCT month || '-01' AS month, MAX(is_partial_month) AS is_partial_month
    FROM clean GROUP BY month
),
last_full AS (SELECT MAX(month) AS l FROM months WHERE is_partial_month = 0)
SELECT
    m.month,
    CAST(substr(m.month, 1, 4) AS INTEGER)                         AS year,
    'Q' || ((CAST(substr(m.month, 6, 2) AS INTEGER) + 2) / 3)      AS quarter,
    substr(m.month, 1, 7)                                          AS month_label,
    m.is_partial_month,
    -- months between this month and L (0 = L, 11 = 11 months earlier)
    (CAST(substr(l.l, 1, 4) AS INTEGER) * 12 + CAST(substr(l.l, 6, 2) AS INTEGER))
      - (CAST(substr(m.month, 1, 4) AS INTEGER) * 12 + CAST(substr(m.month, 6, 2) AS INTEGER)) AS months_before_last_full,
    CASE WHEN m.is_partial_month = 0 AND m.month > date(l.l, '-12 months') THEN 1 ELSE 0 END AS is_latest_12m,
    CASE WHEN m.month > date(l.l, '-24 months') AND m.month <= date(l.l, '-12 months') THEN 1 ELSE 0 END AS is_prior_12m,
    CASE WHEN m.is_partial_month = 0 AND m.month > date(l.l, '-24 months') THEN 1 ELSE 0 END AS is_recent_24m
FROM months m CROSS JOIN last_full l;

DROP TABLE IF EXISTS dim_town;
CREATE TABLE dim_town AS SELECT DISTINCT town FROM clean ORDER BY town;

DROP TABLE IF EXISTS dim_flat_type;
CREATE TABLE dim_flat_type AS
SELECT DISTINCT flat_type,
    CASE flat_type WHEN '1 ROOM' THEN 1 WHEN '2 ROOM' THEN 2 WHEN '3 ROOM' THEN 3 WHEN '4 ROOM' THEN 4
                   WHEN '5 ROOM' THEN 5 WHEN 'EXECUTIVE' THEN 6 WHEN 'MULTI-GENERATION' THEN 7 ELSE 99 END AS flat_type_order
FROM clean;

DROP TABLE IF EXISTS dim_storey_range;
CREATE TABLE dim_storey_range AS
SELECT DISTINCT storey_range, storey_lower AS storey_order,
       -- display label, e.g. '01 TO 03' -> 'Floors 1-3'
       'Floors ' || CAST(substr(storey_range, 1, 2) AS INTEGER) || '-' ||
       CAST(substr(storey_range, 7, 2) AS INTEGER) AS storey_label
FROM clean;

DROP TABLE IF EXISTS dim_flat_model;
CREATE TABLE dim_flat_model AS SELECT DISTINCT flat_model FROM clean ORDER BY flat_model;
