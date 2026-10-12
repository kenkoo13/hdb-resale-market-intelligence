-- 02_aggregates.sql
-- Pre-aggregated summaries used (a) as independent SQL cross-checks of the pandas
-- results and the DAX measures, and (b) as small committed CSVs browsable on GitHub.
-- SQLite has no MEDIAN(): the median is the mean of the middle one or two values of
-- the ordered group, which equals pandas Series.median() and DAX MEDIAN().

DROP TABLE IF EXISTS agg_monthly;
CREATE TABLE agg_monthly AS
WITH ranked AS (
    SELECT f.month, f.resale_price,
           ROW_NUMBER() OVER (PARTITION BY f.month ORDER BY f.resale_price) AS rn,
           COUNT(*)     OVER (PARTITION BY f.month)                         AS cnt
    FROM fact_transactions f
)
SELECT r.month, r.cnt AS transactions, AVG(r.resale_price) AS median_price, d.is_partial_month
FROM ranked r JOIN dim_month d ON d.month = r.month
WHERE r.rn IN ((r.cnt + 1) / 2, (r.cnt + 2) / 2)
GROUP BY r.month ORDER BY r.month;

DROP TABLE IF EXISTS agg_town_flat_type_latest12;
CREATE TABLE agg_town_flat_type_latest12 AS
WITH base AS (
    SELECT f.town, f.flat_type, f.resale_price
    FROM fact_transactions f JOIN dim_month d ON d.month = f.month
    WHERE d.is_latest_12m = 1
),
ranked AS (
    SELECT town, flat_type, resale_price,
           ROW_NUMBER() OVER (PARTITION BY town, flat_type ORDER BY resale_price) AS rn,
           COUNT(*)     OVER (PARTITION BY town, flat_type)                         AS cnt
    FROM base
)
SELECT town, flat_type, cnt AS transactions, AVG(resale_price) AS median_price,
       CASE WHEN cnt < 30 THEN 1 ELSE 0 END AS low_sample
FROM ranked
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
GROUP BY town, flat_type ORDER BY town, flat_type;
