-- Business Question: Do new shoppers come back after their first visit
-- (D7/D14/D28 return within N days, exact-day D1..D28 retention curve,
-- and 28-day repeat-purchase rate after first purchase)?

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
        MIN(event_date) AS first_seen_date,
        DATE_TRUNC('week', MIN(event_date))::DATE AS cohort_week
    FROM user_days
    GROUP BY user_id
),
-- Exclude users first seen in the first 7 days (likely existing users)
eligible_users AS (
    SELECT
        u.user_id,
        u.first_seen_date,
        u.cohort_week,
        b.max_date
    FROM user_first_seen u
    CROSS JOIN bounds b
    WHERE u.first_seen_date >= b.min_date + INTERVAL '7 days'
),
user_return_windows AS (
    SELECT
        e.user_id,
        e.cohort_week,
        e.first_seen_date,
        e.max_date,
        CASE WHEN e.first_seen_date <= e.max_date - INTERVAL '7 days' THEN 1 ELSE 0 END AS eligible_d7,
        CASE WHEN e.first_seen_date <= e.max_date - INTERVAL '14 days' THEN 1 ELSE 0 END AS eligible_d14,
        CASE WHEN e.first_seen_date <= e.max_date - INTERVAL '28 days' THEN 1 ELSE 0 END AS eligible_d28,
        MAX(CASE WHEN d.event_date BETWEEN e.first_seen_date + 1 AND e.first_seen_date + 7 THEN 1 ELSE 0 END) AS returned_d7,
        MAX(CASE WHEN d.event_date BETWEEN e.first_seen_date + 1 AND e.first_seen_date + 14 THEN 1 ELSE 0 END) AS returned_d14,
        MAX(CASE WHEN d.event_date BETWEEN e.first_seen_date + 1 AND e.first_seen_date + 28 THEN 1 ELSE 0 END) AS returned_d28
    FROM eligible_users e
    LEFT JOIN user_days d
        ON e.user_id = d.user_id
       AND d.event_date > e.first_seen_date
       AND d.event_date <= e.first_seen_date + 28
    GROUP BY e.user_id, e.cohort_week, e.first_seen_date, e.max_date
),
cohort_summary AS (
    SELECT
        cohort_week,
        COUNT(*)::BIGINT AS cohort_users,
        SUM(eligible_d7)::BIGINT AS eligible_d7_users,
        SUM(CASE WHEN eligible_d7 = 1 THEN returned_d7 ELSE 0 END)::BIGINT AS returned_d7_users,
        ROUND(SUM(CASE WHEN eligible_d7 = 1 THEN returned_d7 ELSE 0 END) * 1.0 / NULLIF(SUM(eligible_d7), 0), 6) AS d7_return_rate,
        SUM(eligible_d14)::BIGINT AS eligible_d14_users,
        SUM(CASE WHEN eligible_d14 = 1 THEN returned_d14 ELSE 0 END)::BIGINT AS returned_d14_users,
        ROUND(SUM(CASE WHEN eligible_d14 = 1 THEN returned_d14 ELSE 0 END) * 1.0 / NULLIF(SUM(eligible_d14), 0), 6) AS d14_return_rate,
        SUM(eligible_d28)::BIGINT AS eligible_d28_users,
        SUM(CASE WHEN eligible_d28 = 1 THEN returned_d28 ELSE 0 END)::BIGINT AS returned_d28_users,
        ROUND(SUM(CASE WHEN eligible_d28 = 1 THEN returned_d28 ELSE 0 END) * 1.0 / NULLIF(SUM(eligible_d28), 0), 6) AS d28_return_rate
    FROM user_return_windows
    GROUP BY cohort_week
)
SELECT
    cohort_week,
    cohort_users,
    eligible_d7_users,
    returned_d7_users,
    d7_return_rate,
    eligible_d14_users,
    returned_d14_users,
    d14_return_rate,
    eligible_d28_users,
    returned_d28_users,
    d28_return_rate,
    SUM(cohort_users) OVER () AS total_eligible_cohort_users
FROM cohort_summary
ORDER BY cohort_week;
