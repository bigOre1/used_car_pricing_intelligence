-- =============================================================================
--  USED CAR PRICING INTELLIGENCE SUITE
--  SQL Analysis Queries
--  Author: Ore Atobatele
-- =============================================================================
--  Demonstrates: CTEs, Window Functions, Subqueries, Aggregations,
--                CASE logic, JOINs, Ranking, Rolling Averages, and
--                Cohort Analysis — all applied to real pricing problems.
-- =============================================================================


-- =============================================================================
-- 1. REVENUE SUMMARY BY MAKE & SEGMENT
--    Top-line revenue, gross profit, and margin by brand
-- =============================================================================
SELECT
    make,
    COUNT(*)                                        AS units_sold,
    ROUND(SUM(sale_price), 2)                       AS total_revenue,
    ROUND(SUM(gross_profit), 2)                     AS total_gross_profit,
    ROUND(AVG(gross_margin_pct), 2)                 AS avg_margin_pct,
    ROUND(AVG(sale_price), 2)                       AS avg_sale_price,
    ROUND(AVG(days_in_inventory), 1)                AS avg_days_to_sale
FROM vehicles
GROUP BY make
ORDER BY total_revenue DESC;


-- =============================================================================
-- 2. PRICING VARIANCE vs. MARKET BENCHMARK
--    Identify which make/model/year combos we're pricing above or below market
-- =============================================================================
SELECT
    v.make,
    v.model,
    v.year,
    v.condition,
    ROUND(AVG(v.sale_price), 2)                     AS avg_our_price,
    ROUND(b.market_avg_price, 2)                    AS market_avg_price,
    ROUND(AVG(v.sale_price) - b.market_avg_price, 2) AS price_variance,
    ROUND(((AVG(v.sale_price) - b.market_avg_price)
           / b.market_avg_price) * 100, 2)          AS variance_pct
FROM vehicles v
JOIN market_benchmarks b
    ON  v.make      = b.make
    AND v.model     = b.model
    AND v.year      = b.year
    AND v.condition = b.condition
GROUP BY v.make, v.model, v.year, v.condition
ORDER BY ABS(variance_pct) DESC
LIMIT 20;


-- =============================================================================
-- 3. INVENTORY AGING ANALYSIS
--    Classify inventory age and calculate potential revenue at risk
-- =============================================================================
SELECT
    CASE
        WHEN days_in_inventory <= 15 THEN '0-15 Days (Hot)'
        WHEN days_in_inventory <= 30 THEN '16-30 Days (Active)'
        WHEN days_in_inventory <= 60 THEN '31-60 Days (Aging)'
        WHEN days_in_inventory <= 90 THEN '61-90 Days (Stale)'
        ELSE '90+ Days (Critical)'
    END                                             AS aging_bucket,
    COUNT(*)                                        AS units,
    ROUND(AVG(sale_price), 2)                       AS avg_sale_price,
    ROUND(SUM(gross_profit), 2)                     AS total_gross_profit,
    ROUND(AVG(gross_margin_pct), 2)                 AS avg_margin_pct,
    ROUND(AVG(days_in_inventory), 1)                AS avg_days
FROM vehicles
GROUP BY aging_bucket
ORDER BY MIN(days_in_inventory);


-- =============================================================================
-- 4. MONTHLY REVENUE TREND WITH 3-MONTH ROLLING AVERAGE
--    Uses window functions to smooth revenue trends for forecasting
-- =============================================================================
WITH monthly_rev AS (
    SELECT
        sale_year,
        sale_month,
        COUNT(*)                    AS units_sold,
        ROUND(SUM(sale_price), 2)   AS monthly_revenue,
        ROUND(SUM(gross_profit), 2) AS monthly_profit
    FROM vehicles
    GROUP BY sale_year, sale_month
),
rolling AS (
    SELECT
        sale_year,
        sale_month,
        units_sold,
        monthly_revenue,
        monthly_profit,
        ROUND(AVG(monthly_revenue) OVER (
            ORDER BY sale_year, sale_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2)                       AS revenue_3mo_rolling_avg,
        ROUND(AVG(monthly_profit) OVER (
            ORDER BY sale_year, sale_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2)                       AS profit_3mo_rolling_avg
    FROM monthly_rev
)
SELECT * FROM rolling
ORDER BY sale_year, sale_month;


-- =============================================================================
-- 5. SALESPERSON PERFORMANCE SCORECARD
--    Rank salespeople by revenue, margin, and deals closed
-- =============================================================================
WITH sp_stats AS (
    SELECT
        salesperson,
        COUNT(*)                            AS deals_closed,
        ROUND(SUM(sale_price), 2)           AS total_revenue,
        ROUND(AVG(gross_margin_pct), 2)     AS avg_margin_pct,
        ROUND(AVG(days_in_inventory), 1)    AS avg_days_to_close,
        ROUND(SUM(gross_profit), 2)         AS total_profit
    FROM vehicles
    GROUP BY salesperson
)
SELECT
    salesperson,
    deals_closed,
    total_revenue,
    total_profit,
    avg_margin_pct,
    avg_days_to_close,
    RANK() OVER (ORDER BY total_revenue DESC)   AS revenue_rank,
    RANK() OVER (ORDER BY avg_margin_pct DESC)  AS margin_rank,
    RANK() OVER (ORDER BY avg_days_to_close)    AS speed_rank
FROM sp_stats
ORDER BY revenue_rank;


-- =============================================================================
-- 6. SEASONALITY ANALYSIS — Best & Worst Selling Months
--    Month-over-month indexed to annual average (index > 100 = above avg)
-- =============================================================================
WITH monthly_avg AS (
    SELECT
        sale_month,
        COUNT(*)                            AS units_sold,
        ROUND(AVG(sale_price), 2)           AS avg_price,
        ROUND(AVG(gross_margin_pct), 2)     AS avg_margin
    FROM vehicles
    GROUP BY sale_month
),
overall AS (
    SELECT AVG(units_sold) AS baseline FROM monthly_avg
)
SELECT
    m.sale_month,
    CASE m.sale_month
        WHEN 1 THEN 'January'   WHEN 2  THEN 'February' WHEN 3  THEN 'March'
        WHEN 4 THEN 'April'     WHEN 5  THEN 'May'       WHEN 6  THEN 'June'
        WHEN 7 THEN 'July'      WHEN 8  THEN 'August'    WHEN 9  THEN 'September'
        WHEN 10 THEN 'October'  WHEN 11 THEN 'November'  WHEN 12 THEN 'December'
    END                                                 AS month_name,
    m.units_sold,
    m.avg_price,
    m.avg_margin,
    ROUND((m.units_sold / o.baseline) * 100, 1)        AS seasonality_index
FROM monthly_avg m, overall o
ORDER BY m.sale_month;


-- =============================================================================
-- 7. CONDITION-BASED PROFITABILITY DEEP DIVE
--    Margin and turn rate by vehicle condition — guides acquisition strategy
-- =============================================================================
SELECT
    condition,
    COUNT(*)                                        AS units,
    ROUND(AVG(acquisition_cost), 2)                 AS avg_acquisition_cost,
    ROUND(AVG(sale_price), 2)                       AS avg_sale_price,
    ROUND(AVG(gross_profit), 2)                     AS avg_gross_profit,
    ROUND(AVG(gross_margin_pct), 2)                 AS avg_margin_pct,
    ROUND(AVG(days_in_inventory), 1)                AS avg_days_to_sale,
    ROUND(SUM(gross_profit) / SUM(days_in_inventory), 2) AS profit_per_day_on_lot
FROM vehicles
GROUP BY condition
ORDER BY profit_per_day_on_lot DESC;


-- =============================================================================
-- 8. PRICE ELASTICITY PROXY — Discount Depth vs. Days on Lot
--    How aggressively are we discounting aging inventory?
-- =============================================================================
SELECT
    CASE
        WHEN days_in_inventory <= 30 THEN '0-30 days'
        WHEN days_in_inventory <= 60 THEN '31-60 days'
        WHEN days_in_inventory <= 90 THEN '61-90 days'
        ELSE '90+ days'
    END                                             AS age_bucket,
    COUNT(*)                                        AS units,
    ROUND(AVG((list_price - sale_price) / list_price * 100), 2) AS avg_discount_pct,
    ROUND(AVG(gross_margin_pct), 2)                 AS avg_margin_pct,
    ROUND(AVG(sale_price), 2)                       AS avg_sale_price
FROM vehicles
GROUP BY age_bucket
ORDER BY MIN(days_in_inventory);


-- =============================================================================
-- 9. TOP 10 MOST PROFITABLE VEHICLE SEGMENTS (Make + Model)
--    Best ROI vehicles to prioritize in acquisition
-- =============================================================================
WITH segment_perf AS (
    SELECT
        make,
        model,
        COUNT(*)                                    AS units_sold,
        ROUND(AVG(gross_profit), 2)                 AS avg_gross_profit,
        ROUND(AVG(gross_margin_pct), 2)             AS avg_margin_pct,
        ROUND(AVG(days_in_inventory), 1)            AS avg_days_to_sale,
        ROUND(SUM(gross_profit), 2)                 AS total_profit,
        ROUND(AVG(gross_profit) / AVG(days_in_inventory), 2) AS profit_per_day
    FROM vehicles
    GROUP BY make, model
    HAVING units_sold >= 3
)
SELECT
    make,
    model,
    units_sold,
    avg_gross_profit,
    avg_margin_pct,
    avg_days_to_sale,
    total_profit,
    profit_per_day,
    RANK() OVER (ORDER BY profit_per_day DESC)      AS profitability_rank
FROM segment_perf
ORDER BY profitability_rank
LIMIT 10;


-- =============================================================================
-- 10. YEAR-OVER-YEAR PERFORMANCE COMPARISON (2024 vs 2025 YTD)
-- =============================================================================
WITH yearly AS (
    SELECT
        sale_year,
        sale_month,
        SUM(sale_price)     AS revenue,
        SUM(gross_profit)   AS profit,
        COUNT(*)            AS units
    FROM vehicles
    GROUP BY sale_year, sale_month
),
pivot AS (
    SELECT
        sale_month,
        ROUND(SUM(CASE WHEN sale_year = 2024 THEN revenue END), 2)  AS rev_2024,
        ROUND(SUM(CASE WHEN sale_year = 2025 THEN revenue END), 2)  AS rev_2025,
        SUM(CASE WHEN sale_year = 2024 THEN units END)              AS units_2024,
        SUM(CASE WHEN sale_year = 2025 THEN units END)              AS units_2025
    FROM yearly
    GROUP BY sale_month
)
SELECT
    sale_month,
    rev_2024,
    rev_2025,
    ROUND(((rev_2025 - rev_2024) / NULLIF(rev_2024, 0)) * 100, 1)  AS revenue_yoy_pct,
    units_2024,
    units_2025
FROM pivot
WHERE rev_2024 IS NOT NULL AND rev_2025 IS NOT NULL
ORDER BY sale_month;


-- =============================================================================
-- 11. COHORT ANALYSIS — Acquisition Cost Efficiency by Vehicle Age
--    Are older vehicles generating competitive returns?
-- =============================================================================
SELECT
    (2025 - year)                                   AS vehicle_age_yrs,
    COUNT(*)                                        AS units,
    ROUND(AVG(acquisition_cost), 2)                 AS avg_acquisition_cost,
    ROUND(AVG(sale_price), 2)                       AS avg_sale_price,
    ROUND(AVG(gross_margin_pct), 2)                 AS avg_margin_pct,
    ROUND(AVG(days_in_inventory), 1)                AS avg_days_to_sale,
    ROUND(AVG(gross_profit / acquisition_cost * 100), 2) AS roi_pct
FROM vehicles
GROUP BY vehicle_age_yrs
ORDER BY vehicle_age_yrs;


-- =============================================================================
-- 12. UNDERPRICED VEHICLE ALERT
--    Vehicles sold significantly below market benchmark — revenue leakage signal
-- =============================================================================
SELECT
    v.vin,
    v.make,
    v.model,
    v.year,
    v.condition,
    v.sale_price,
    b.market_avg_price,
    ROUND(b.market_avg_price - v.sale_price, 2)     AS left_on_table,
    v.days_in_inventory,
    v.salesperson
FROM vehicles v
JOIN market_benchmarks b
    ON  v.make = b.make AND v.model = b.model
    AND v.year = b.year AND v.condition = b.condition
WHERE v.sale_price < b.market_avg_price * 0.93
ORDER BY left_on_table DESC
LIMIT 15;
