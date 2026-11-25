-- Business Question: What is the exact-day D1..D28 retention curve for new
-- shoppers, and what share of first-time buyers make a repeat purchase within 28 days?

WITH bounds AS (
    SELECT
        MIN(CAST(event_time AS DATE)) AS min_date,
        MAX(CAST(event_time AS DATE)) AS max_date
    FROM events_source
),
user_days AS (
    SELECT DISTINCT
        user_id,
        CAST(event_time AS DATE) AS event_date
    FROM events_source
    WHERE user_id IS NOT NULL
),
user_first_seen AS (
    SELECT
        user_id,
        MIN(event_date) AS first_seen_date
    FROM user_days
    GROUP BY user_id
),
eligible_users AS (
    SELECT
        u.user_id,
        u.first_seen_date,
        b.max_date
    FROM user_first_seen u
    CROSS JOIN bounds b
    WHERE u.first_seen_date >= b.min_date + INTERVAL '7 days'
),
day_offsets AS (
    SELECT CAST(UNNEST(GENERATE_SERIES(1, 28)) AS INTEGER) AS day_n
),
exact_day_retention AS (
    SELECT
        o.day_n,
        COUNT(DISTINCT CASE WHEN e.first_seen_date <= e.max_date - o.day_n THEN e.user_id END)::BIGINT AS eligible_users,
        COUNT(DISTINCT CASE WHEN e.first_seen_date <= e.max_date - o.day_n AND d.event_date = e.first_seen_date + o.day_n THEN e.user_id END)::BIGINT AS retained_users
    FROM day_offsets o
    CROSS JOIN eligible_users e
    LEFT JOIN user_days d
        ON e.user_id = d.user_id
       AND d.event_date = e.first_seen_date + o.day_n
    GROUP BY o.day_n
),
buyer_purchases AS (
    SELECT DISTINCT
        user_id,
        CAST(event_time AS DATE) AS purchase_date
    FROM events_source
    WHERE event_type = 'purchase'
      AND user_id IS NOT NULL
),
first_buyers AS (
    SELECT
        p.user_id,
        MIN(p.purchase_date) AS first_purchase_date,
        b.max_date
    FROM buyer_purchases p
    CROSS JOIN bounds b
    GROUP BY p.user_id, b.min_date, b.max_date
    HAVING MIN(p.purchase_date) >= b.min_date + INTERVAL '7 days'
       AND MIN(p.purchase_date) <= b.max_date - 28
),
repeat_buyers AS (
    SELECT
        fb.user_id,
        MAX(CASE WHEN bp.purchase_date BETWEEN fb.first_purchase_date + 1 AND fb.first_purchase_date + 28 THEN 1 ELSE 0 END) AS repeated_28d
    FROM first_buyers fb
    LEFT JOIN buyer_purchases bp
        ON fb.user_id = bp.user_id
       AND bp.purchase_date > fb.first_purchase_date
       AND bp.purchase_date <= fb.first_purchase_date + 28
    GROUP BY fb.user_id
)
SELECT
    'exact_day_curve' AS metric_type,
    day_n,
    eligible_users,
    retained_users,
    ROUND(retained_users * 1.0 / NULLIF(eligible_users, 0), 6) AS rate,
    SUM(retained_users) OVER (ORDER BY day_n) AS cumulative_retained_user_days
FROM exact_day_retention

UNION ALL

SELECT
    'repeat_purchase_28d' AS metric_type,
    28 AS day_n,
    COUNT(*)::BIGINT AS eligible_users,
    SUM(repeated_28d)::BIGINT AS retained_users,
    ROUND(SUM(repeated_28d) * 1.0 / NULLIF(COUNT(*), 0), 6) AS rate,
    SUM(repeated_28d)::BIGINT AS cumulative_retained_user_days
FROM repeat_buyers
ORDER BY metric_type, day_n;
