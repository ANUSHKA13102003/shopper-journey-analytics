-- Business Question: Where do online shoppers drop off in the session funnel
-- (view -> cart -> purchase), how does conversion vary by top-level category,
-- price band, weekday, and hour, and how long does it take to purchase?

WITH clean_events AS (
    SELECT
        event_time,
        CAST(event_time AS DATE) AS event_date,
        EXTRACT('dow' FROM event_time) AS weekday_num,
        STRFTIME(event_time, '%a') AS weekday_name,
        EXTRACT('hour' FROM event_time) AS event_hour,
        event_type,
        product_id,
        COALESCE(NULLIF(SPLIT_PART(category_code, '.', 1), ''), 'unknown') AS top_category,
        price,
        CASE
            WHEN price IS NULL OR price <= 0 THEN 'invalid_or_free'
            WHEN price < 25 THEN 'under_25'
            WHEN price < 100 THEN '25_to_99'
            WHEN price < 300 THEN '100_to_299'
            ELSE '300_plus'
        END AS price_band,
        user_id,
        user_session
    FROM events_source
    WHERE user_session IS NOT NULL
      AND user_id IS NOT NULL
),
session_flags AS (
    SELECT
        user_session,
        ANY_VALUE(user_id) AS user_id,
        MIN(event_time) AS session_start,
        ANY_VALUE(weekday_num) AS weekday_num,
        ANY_VALUE(weekday_name) AS weekday_name,
        ANY_VALUE(event_hour) AS event_hour,
        MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS has_view,
        MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS has_purchase,
        MIN(CASE WHEN event_type = 'view' THEN event_time END) AS first_view_time,
        MIN(CASE WHEN event_type = 'purchase' THEN event_time END) AS first_purchase_time,
        ARG_MIN(top_category, event_time) AS entry_category,
        ARG_MIN(price_band, event_time) FILTER (WHERE price > 0) AS entry_price_band,
        SUM(CASE WHEN event_type = 'purchase' AND price > 0 THEN price ELSE 0 END) AS session_revenue
    FROM clean_events
    GROUP BY user_session
),
funnel_steps AS (
    SELECT
        user_session,
        weekday_num,
        weekday_name,
        event_hour,
        entry_category,
        COALESCE(entry_price_band, 'invalid_or_free') AS price_band,
        has_view,
        CASE WHEN has_view = 1 AND has_cart = 1 THEN 1 ELSE 0 END AS reached_cart,
        CASE WHEN has_view = 1 AND has_cart = 1 AND has_purchase = 1 THEN 1 ELSE 0 END AS reached_purchase,
        CASE WHEN has_cart = 1 AND has_purchase = 0 THEN 1 ELSE 0 END AS cart_abandoned,
        CASE
            WHEN has_view = 1 AND has_purchase = 1 AND first_purchase_time >= first_view_time
            THEN DATE_DIFF('second', first_view_time, first_purchase_time) / 60.0
        END AS minutes_view_to_purchase,
        session_revenue,
        ROW_NUMBER() OVER (ORDER BY session_start, user_session) AS session_seq
    FROM session_flags
    WHERE has_view = 1
)
SELECT
    'overall' AS breakdown_type,
    'all' AS breakdown_value,
    0 AS sort_order,
    COUNT(*)::BIGINT AS sessions_viewed,
    SUM(reached_cart)::BIGINT AS sessions_carted,
    SUM(reached_purchase)::BIGINT AS sessions_purchased,
    SUM(cart_abandoned)::BIGINT AS sessions_cart_abandoned,
    ROUND(SUM(reached_cart) * 1.0 / NULLIF(COUNT(*), 0), 6) AS view_to_cart_rate,
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(SUM(reached_cart), 0), 6) AS cart_to_purchase_rate,
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(COUNT(*), 0), 6) AS view_to_purchase_rate,
    ROUND(SUM(cart_abandoned) * 1.0 / NULLIF(SUM(reached_cart), 0), 6) AS cart_abandonment_rate,
    ROUND(MEDIAN(minutes_view_to_purchase), 2) AS median_minutes_to_purchase,
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.25), 2) AS p25_minutes_to_purchase,
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.75), 2) AS p75_minutes_to_purchase,
    ROUND(SUM(session_revenue), 2) AS total_revenue
FROM funnel_steps

UNION ALL

SELECT
    'category' AS breakdown_type,
    entry_category AS breakdown_value,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS sort_order,
    COUNT(*)::BIGINT,
    SUM(reached_cart)::BIGINT,
    SUM(reached_purchase)::BIGINT,
    SUM(cart_abandoned)::BIGINT,
    ROUND(SUM(reached_cart) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(cart_abandoned) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(MEDIAN(minutes_view_to_purchase), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.25), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.75), 2),
    ROUND(SUM(session_revenue), 2)
FROM funnel_steps
GROUP BY entry_category

UNION ALL

SELECT
    'price_band' AS breakdown_type,
    price_band AS breakdown_value,
    CASE price_band
        WHEN 'under_25' THEN 1
        WHEN '25_to_99' THEN 2
        WHEN '100_to_299' THEN 3
        WHEN '300_plus' THEN 4
        ELSE 5
    END AS sort_order,
    COUNT(*)::BIGINT,
    SUM(reached_cart)::BIGINT,
    SUM(reached_purchase)::BIGINT,
    SUM(cart_abandoned)::BIGINT,
    ROUND(SUM(reached_cart) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(cart_abandoned) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(MEDIAN(minutes_view_to_purchase), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.25), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.75), 2),
    ROUND(SUM(session_revenue), 2)
FROM funnel_steps
GROUP BY price_band

UNION ALL

SELECT
    'weekday' AS breakdown_type,
    weekday_name AS breakdown_value,
    weekday_num AS sort_order,
    COUNT(*)::BIGINT,
    SUM(reached_cart)::BIGINT,
    SUM(reached_purchase)::BIGINT,
    SUM(cart_abandoned)::BIGINT,
    ROUND(SUM(reached_cart) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(cart_abandoned) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(MEDIAN(minutes_view_to_purchase), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.25), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.75), 2),
    ROUND(SUM(session_revenue), 2)
FROM funnel_steps
GROUP BY weekday_name, weekday_num

UNION ALL

SELECT
    'hour' AS breakdown_type,
    LPAD(CAST(event_hour AS VARCHAR), 2, '0') AS breakdown_value,
    event_hour AS sort_order,
    COUNT(*)::BIGINT,
    SUM(reached_cart)::BIGINT,
    SUM(reached_purchase)::BIGINT,
    SUM(cart_abandoned)::BIGINT,
    ROUND(SUM(reached_cart) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(SUM(reached_purchase) * 1.0 / NULLIF(COUNT(*), 0), 6),
    ROUND(SUM(cart_abandoned) * 1.0 / NULLIF(SUM(reached_cart), 0), 6),
    ROUND(MEDIAN(minutes_view_to_purchase), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.25), 2),
    ROUND(QUANTILE_CONT(minutes_view_to_purchase, 0.75), 2),
    ROUND(SUM(session_revenue), 2)
FROM funnel_steps
GROUP BY event_hour;
