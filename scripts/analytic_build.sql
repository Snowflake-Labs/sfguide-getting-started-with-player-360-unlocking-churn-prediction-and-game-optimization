USE ROLE SYSADMIN;
USE WAREHOUSE PLAYER_360_BUILD_WH;
USE SCHEMA PLAYER_360.ANALYTIC;

-- 1. Create Dynamic Table Representing the Rentention Information
create or replace dynamic table PLAYER_360.ANALYTIC.RETENTION(
	USER_ID,
	FIRST_LOGIN_DATE,
	LAST_LOGIN_DATE,
	TOTAL_LOGINS,
	LOGGED_IN_AFTER_1_DAY,
	LOGGED_IN_AFTER_7_DAYS,
	LOGGED_IN_AFTER_30_DAYS,
	LOGGED_IN_IN_LAST_30_DAYS,
	DAYS_SINCE_LAST_LOGIN,
	CHURNED
) target_lag = '1 days' refresh_mode = AUTO initialize = ON_CREATE warehouse = PLAYER_360_BUILD_WH
 as
WITH first_login AS (
    SELECT
        user_ID,
        MIN(LOG_IN) AS first_login_date,
        MAX(LOG_IN) AS last_login_date,
        COUNT(*) AS total_logins
    FROM PLAYER_360.RAW.SESSIONS
    GROUP BY user_ID
),
login_activity AS (
    SELECT
        f.user_ID,
        f.first_login_date,
        f.last_login_date,
        f.total_logins,
        IFF(MAX(DATEDIFF(day, f.first_login_date, e.LOG_IN) >= 1), TRUE, FALSE) AS logged_in_after_1_day,
        IFF(MAX(DATEDIFF(day, f.first_login_date, e.LOG_IN) >= 7), TRUE, FALSE) AS logged_in_after_7_days,
        IFF(MAX(DATEDIFF(day, f.first_login_date, e.LOG_IN) >= 30), TRUE, FALSE) AS logged_in_after_30_days,
        IFF(MAX(e.LOG_IN >= DATEADD(day, -30, CURRENT_DATE())), TRUE, FALSE) AS logged_in_in_last_30_days,
        DATEDIFF(day, f.last_login_date, CURRENT_DATE()) AS days_since_last_login
    FROM first_login f
    LEFT JOIN PLAYER_360.RAW.SESSIONS e ON e.user_ID = f.user_ID
    GROUP BY f.user_ID, f.first_login_date, f.last_login_date, f.total_logins
)
SELECT *,
    IFF(days_since_last_login > 30, 1, 0) AS churned
FROM login_activity;

-- 2. Create the Points Mapping Table to give Points Metrics 
CREATE OR REPLACE TABLE PLAYER_360.ANALYTIC.POINTS_MAPPING_TABLE (
    EVENT STRING,
    POINTS FLOAT 
); 
INSERT INTO PLAYER_360.ANALYTIC.POINTS_MAPPING_TABLE (EVENT, POINTS)
VALUES ('Assists', 0.2),
       ('Boosts', 0.1),
       ('Damage Dealt', .1),
       ('Kills', 1.0),
       ('Distance Traveled', .2),
       ('Weapons Acquired', .1),
       ('Head Shots',.3),
       ('Heals',.2);

-- 3. CREATE Dynamic Table Presenting Points Per Event
CREATE OR REPLACE DYNAMIC TABLE PLAYER_360.ANALYTIC.points_per_event
WAREHOUSE = PLAYER_360_BUILD_WH
TARGET_LAG = '5 minute'
REFRESH_MODE = AUTO
INITIALIZE = ON_CREATE
AS
WITH player_points_per_event AS (
    SELECT
        ge.USER_ID,
        ge.session_id,
        -- Multiply each event occurrence by its point value from the points_mapping_table
        ge.ASSISTS * (SELECT points FROM points_mapping_table WHERE event = 'Assists') AS assist_points,
        ge.BOOSTS * (SELECT points FROM points_mapping_table WHERE event = 'Boosts') AS boost_points,
        ge.DAMAGE_DEALT * (SELECT points FROM points_mapping_table WHERE event = 'Damage Dealt') AS damage_points,
        ge.DISTANCE_TRAVELED * (SELECT points FROM points_mapping_table WHERE event = 'Distance Traveled') AS distance_points,
        ge.KILLS * (SELECT points FROM points_mapping_table WHERE event = 'Kills') AS kill_points,
        ge.WEAPONS_ACQUIRED * (SELECT points FROM points_mapping_table WHERE event = 'Weapons Acquired') AS weapon_points,
        ge.HEADSHOTS * (SELECT points FROM points_mapping_table WHERE event = 'Head Shots') AS headshot_points,
        ge.HEALS * (SELECT points FROM points_mapping_table WHERE event = 'Heals') AS heals_points
    FROM
        PLAYER_360.RAW.GAME_EVENTS ge
),
player_points_per_session AS (
    -- Step 2: Sum up the total points for each user and show a breakdown of points by event type
    SELECT
        USER_ID,
        SESSION_ID,
        SUM(assist_points) AS ASSISTS_POINTS,
        SUM(boost_points) AS BOOSTS_POINTS,
        SUM(damage_points) AS DAMAGE_POINTS,
        SUM(distance_points) AS DISTANCE_POINTS,
        SUM(kill_points) AS KILLS_POINTS,
        SUM(weapon_points) AS WEAPONS_POINTS,
        SUM(headshot_points) AS HEADSHOTS_POINTS,
        SUM(heals_points) AS HEALS_POINTS,
        SUM(assist_points + boost_points + damage_points + distance_points + kill_points + weapon_points + headshot_points + heals_points) AS TOTAL_POINTS
    FROM
        player_points_per_event ppe
    GROUP BY
        USER_ID, SESSION_ID
)
SELECT 
        pps.USER_ID,
        pps.SESSION_ID,
        s.log_in,
        s.log_out,
        s.session_duration_minutes,
        ASSISTS_POINTS,
        BOOSTS_POINTS,
        DAMAGE_POINTS,
        DISTANCE_POINTS,
        KILLS_POINTS,
        WEAPONS_POINTS,
        HEADSHOTS_POINTS,
        HEALS_POINTS,
        TOTAL_POINTS
FROM player_points_per_session pps
LEFT JOIN PLAYER_360.RAW.SESSIONS s 
ON pps.SESSION_ID = s.session_id;

-- 4. We aggregate the points for the player across all sessions
create or replace dynamic table PLAYER_360.ANALYTIC.points_per_user
    TARGET_LAG = '5 minutes'
    refresh_mode = AUTO
    initialize = ON_CREATE
    warehouse = PLAYER_360_BUILD_WH
    as
SELECT
    USER_ID,
    SUM(COALESCE(ASSISTS_POINTS, 0)) AS ASSISTS_POINTS,
    SUM(COALESCE(BOOSTS_POINTS, 0)) AS BOOSTS_POINTS,
    SUM(COALESCE(DAMAGE_POINTS, 0)) AS DAMAGE_POINTS,
    SUM(COALESCE(DISTANCE_POINTS, 0)) AS DISTANCE_POINTS,
    SUM(COALESCE(KILLS_POINTS, 0)) AS KILLS_POINTS,
    SUM(COALESCE(WEAPONS_POINTS, 0)) AS WEAPONS_POINTS,
    SUM(COALESCE(HEADSHOTS_POINTS, 0)) AS HEADSHOTS_POINTS,
    SUM(COALESCE(HEALS_POINTS, 0)) AS HEALS_POINTS,
    SUM(
        COALESCE(ASSISTS_POINTS, 0) +
        COALESCE(BOOSTS_POINTS, 0) +
        COALESCE(DAMAGE_POINTS, 0) +
        COALESCE(DISTANCE_POINTS, 0) +
        COALESCE(KILLS_POINTS, 0) +
        COALESCE(WEAPONS_POINTS, 0) +
        COALESCE(HEADSHOTS_POINTS, 0) +
        COALESCE(HEALS_POINTS, 0)
    ) AS TOTAL_POINTS
FROM
    PLAYER_360.ANALYTIC.points_per_event
GROUP BY
    USER_ID
ORDER BY
    USER_ID;

-- 5. We create player rankings
CREATE OR REPLACE TABLE PLAYER_360.ANALYTIC.RANKING_MAPPING_TABLE (
    RANK_NAME STRING,
    LOWER_BOUND FLOAT,
    UPPER_BOUND FLOAT
);
CREATE OR REPLACE TEMPORARY TABLE percentile_values AS
WITH percentile_values_cte AS (
    SELECT
        PERCENTILE_CONT(0.125) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p12_5,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p25,
        PERCENTILE_CONT(0.375) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p37_5,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p50,
        PERCENTILE_CONT(0.625) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p62_5,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p75,
        PERCENTILE_CONT(0.875) WITHIN GROUP (ORDER BY TOTAL_POINTS) AS p87_5,
        MAX(TOTAL_POINTS) AS p100
    FROM
        PLAYER_360.ANALYTIC.POINTS_PER_USER
)
SELECT * FROM percentile_values_cte;
-- Step 4: Populate the Ranking Mapping Table
-- Insert rank definitions into the ranking mapping table using the calculated percentiles
INSERT INTO PLAYER_360.ANALYTIC.RANKING_MAPPING_TABLE (RANK_NAME, LOWER_BOUND, UPPER_BOUND)
WITH rank_definitions AS (
    SELECT
        'Bronze' AS RANK_NAME, 0 AS LOWER_BOUND, p12_5 AS UPPER_BOUND FROM percentile_values
    UNION ALL
    SELECT
        'Silver', p12_5, p25 FROM percentile_values
    UNION ALL
    SELECT
        'Gold', p25, p37_5 FROM percentile_values
    UNION ALL
    SELECT
        'Platinum', p37_5, p50 FROM percentile_values
    UNION ALL
    SELECT
        'Diamond', p50, p62_5 FROM percentile_values
    UNION ALL
    SELECT
        'Elite', p62_5, p75 FROM percentile_values
    UNION ALL
    SELECT
        'Champion', p75, p87_5 FROM percentile_values
    UNION ALL
    SELECT
        'Unreal', p87_5, 'inf' FROM percentile_values
)
SELECT
    RANK_NAME,
    LOWER_BOUND,
    UPPER_BOUND
FROM
    rank_definitions;

-- 6. Create a Dynamic Table for USER_RANKINGS
CREATE OR REPLACE DYNAMIC TABLE PLAYER_360.ANALYTIC.USER_RANKINGS(
    USER_ID,
    TOTAL_POINTS,
    RANK_NAME,
    PERCENTILE
) TARGET_LAG = '1 days' refresh_mode = AUTO initialize = ON_CREATE warehouse = PLAYER_360_BUILD_WH
AS
WITH RankedPlayers AS (
    SELECT
        utp.USER_ID,
        utp.TOTAL_POINTS,
        drm.RANK_NAME,
        RANK() OVER (ORDER BY utp.TOTAL_POINTS DESC) AS PlayerRank,
        COUNT(*) OVER () AS TotalPlayers
    FROM
        PLAYER_360.ANALYTIC.points_per_user utp
    LEFT JOIN
        PLAYER_360.ANALYTIC.RANKING_MAPPING_TABLE drm
    ON
        utp.TOTAL_POINTS >= drm.LOWER_BOUND
        AND utp.TOTAL_POINTS < drm.UPPER_BOUND
)
SELECT
    USER_ID,
    TOTAL_POINTS,
    RANK_NAME,
    -- Calculate the percentile: (Rank - 1) / Total Players * 100
    ((PlayerRank - 1) / CAST(TotalPlayers AS FLOAT)) * 100 AS PERCENTILE
FROM
    RankedPlayers
ORDER BY
    USER_ID;

-- 7. We create player demographics information
create or replace dynamic table PLAYER_360.ANALYTIC.DEMOGRAPHICS(
	USER_ID,
    FULL_NAME,
	AGE,
	GENDER,
	LOCATION,
	PLAYER_TYPE,
    AVERAGE_SESSIONS_PER_ACTIVE_WEEK,
    AVERAGE_SESSION_DURATION,
	TOTAL_ADS,
	IS_SPENDER,
	AVG_PURCHASE_AMOUNT_PER_AD,
    HAS_SUPPORT_TICKET
) TARGET_LAG = '1 days' refresh_mode = AUTO initialize = ON_CREATE warehouse = PLAYER_360_BUILD_WH
 as
WITH user_activity AS (
    -- Aggregate player activity to figure out if they are hardcore or casual
    SELECT
        e.user_ID,
        COUNT(e.LOG_IN) AS total_sessions,
        SUM(e.session_duration_minutes) AS total_session_duration,
        COUNT(DISTINCT(DATE_TRUNC('week', e.LOG_IN))) AS active_weeks,
        total_sessions/active_weeks AS average_sessions_per_active_week,
        total_session_duration/total_sessions AS average_session_duration
    FROM PLAYER_360.RAW.SESSIONS e
    GROUP BY e.user_ID
),
user_spending AS (
    -- Identify spenders and calculate the total purchases and average purchase amount
    SELECT
        p.user_ID,
        COUNT(p.purchase_ID) AS total_ads,
        IFF(COUNT(CASE WHEN p.purchase_type != 'none' THEN p.purchase_id END) > 2, TRUE, FALSE) AS is_spender,
        COALESCE(AVG(p.purchase_amount), 0) AS avg_purchase_amount_per_ad -- Calculate average purchase amount
    FROM PLAYER_360.RAW.purchases p
    GROUP BY p.user_ID
),
user_engagement AS (
    -- Classify players as hardcore or casual based on their activity
    SELECT
        ua.user_ID,
        ua.total_sessions,
        ua.active_weeks,
        CASE
            WHEN ua.total_sessions / ua.active_weeks > 15 THEN 'Hardcore'
            ELSE 'Casual'
        END AS player_type
    FROM user_activity ua
)
SELECT
    u.user_ID,
    CONCAT(u.first_name, ' ', u.last_name) AS full_name,
    DATEDIFF(year, u.birthdate, CURRENT_DATE()) AS age, -- Calculate age from birthday,
    u.gender,
    u.location,
    ue.player_type,
    ua.average_sessions_per_active_week,
    ua.average_session_duration,
    us.total_ads, -- Total number of purchases
    us.is_spender, -- Whether the user is a spender (more than 2 purchases)
    us.avg_purchase_amount_per_ad, -- Average purchase amount
    st.user_id IS NOT NULL AS has_support_ticket
FROM PLAYER_360.RAW.users u
LEFT JOIN user_engagement ue ON u.user_ID = ue.user_ID
LEFT JOIN user_spending us ON u.user_ID = us.user_ID
LEFT JOIN user_activity ua ON u.user_id = ua.user_ID
LEFT JOIN PLAYER_360.RAW.support_tickets st ON u.user_ID = st.user_ID;

-- 8. Create Ad information over past 30 days
CREATE OR REPLACE DYNAMIC TABLE PLAYER_360.ANALYTIC.AD_ENGAGEMENT (
    USER_ID,
    TOTAL_ADS,
    TOTAL_PURCHASES,
    TOTAL_PURCHASES_AMOUNT,
    PROPORTION_PURCHASED,
    AVERAGE_PURCHASE_AMOUNT,
    AVERAGE_AD_ENGAGEMENT_TIME,
    TOTAL_ADS_LAST_30_DAYS,
    TOTAL_PURCHASES_LAST_30_DAYS,
    TOTAL_PURCHASES_AMOUNT_LAST_30_DAYS,
    PROPORTION_PURCHASED_LAST_30_DAYS,
    AVERAGE_PURCHASE_AMOUNT_LAST_30_DAYS,
    AVERAGE_AD_ENGAGEMENT_TIME_LAST_30_DAYS
) 
TARGET_LAG = '5 minutes' 
REFRESH_MODE = AUTO 
INITIALIZE = ON_CREATE 
WAREHOUSE = PLAYER_360_BUILD_WH
AS
SELECT 
    USER_ID,

    -- Total Ads
    COUNT(AD_INTERACTION_ID) AS total_ads,
    
    -- Total purchases
    COUNT(CASE WHEN PURCHASE_TYPE != 'none' THEN PURCHASE_ID END) AS total_purchases,

    -- Total Purchases Amount
    SUM(PURCHASE_AMOUNT) AS total_purchases_amount,

    -- Proportion of Ads purchased from total ads (avoid division by zero)
    COALESCE(NULLIF(COUNT(CASE WHEN PURCHASE_TYPE != 'none' THEN PURCHASE_ID END), 0) 
        / NULLIF(COUNT(AD_INTERACTION_ID), 0), 0) AS proportion_purchased, 
    
    -- Average purchase amount
    COALESCE(AVG(CASE WHEN PURCHASE_TYPE != 'none' THEN PURCHASE_AMOUNT END),0) AS average_purchase_amount,
    
    -- Average ad engagement time
    AVG(AD_ENGAGEMENT_TIME) AS average_ad_engagement_time,

    -- Total ads seen in the last 30 days per user
    COUNT(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' THEN AD_INTERACTION_ID END) AS total_ads_last_30_days,
    
    -- Total purchases in the last 30 days
    COUNT(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' 
               AND PURCHASE_TYPE != 'none' THEN PURCHASE_ID END) AS total_purchases_last_30_days,

    -- Total purchases amount in the last 30 days
    SUM(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS'
            THEN PURCHASE_AMOUNT END) AS total_purchases_amount_last_30_days,

    -- Proportion of ads seen to purchases made in last 30 days (avoid division by zero)
    COALESCE(NULLIF(COUNT(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' 
                               AND PURCHASE_TYPE != 'none' THEN PURCHASE_ID END), 0) 
        / NULLIF(COUNT(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' THEN AD_INTERACTION_ID END), 0), 0) 
        AS proportion_purchased_last_30_days,
    
    -- Average purchase amount in the last 30 days
    COALESCE(AVG(CASE 
                WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' 
                     AND PURCHASE_TYPE != 'none' 
                THEN PURCHASE_AMOUNT 
            END), 0) AS average_purchase_amount_last_30_days,
    
    -- Average ad engagement time in the last 30 days
    AVG(CASE WHEN TIMESTAMP_OF_PURCHASE >= CURRENT_DATE - INTERVAL '30 DAYS' 
             THEN AD_ENGAGEMENT_TIME END) AS average_ad_engagement_time_last_30_days
    
FROM 
    PLAYER_360.RAW.PURCHASES
GROUP BY 
    USER_ID;

USE ROLE SYSADMIN;
USE WAREHOUSE PLAYER_360_BUILD_WH;
USE SCHEMA PLAYER_360.ANALYTIC;

CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.country_count
AS
SELECT 
    LOCATION AS COUNTRY,
    COUNT(USER_ID) AS TOTAL_PLAYERS
FROM 
    PLAYER_360.RAW.USERS
GROUP BY 
    LOCATION;


CREATE OR REPLACE TABLE PLAYER_360.ANALYTIC.daily_active_users (
    active_date DATE,         -- The date for the daily activity
    active_user_count INT     -- The number of active users on that date
);
-- Insert or update the daily active users table
MERGE INTO PLAYER_360.ANALYTIC.daily_active_users AS dau
USING (
    SELECT
        CAST(LOG_IN AS DATE) AS active_date,    -- Extract the date part from LOG_IN timestamp
        COUNT(DISTINCT USER_ID) AS active_user_count -- Count unique users for that day
    FROM PLAYER_360.RAW.SESSIONS
    GROUP BY CAST(LOG_IN AS DATE)    -- Group by the date part of the login timestamp
) AS daily_activity
ON dau.active_date = daily_activity.active_date
-- If the record exists, update the count of active users, otherwise insert a new record
WHEN MATCHED THEN 
    UPDATE SET dau.active_user_count = daily_activity.active_user_count
WHEN NOT MATCHED THEN
    INSERT (active_date, active_user_count) 
    VALUES (daily_activity.active_date, daily_activity.active_user_count);

CREATE OR REPLACE TASK update_daily_active_users
  WAREHOUSE = PLAYER_360_BUILD_WH
  SCHEDULE = 'USING CRON 0 0 * * * UTC' -- Runs daily at midnight UTC
AS
    MERGE INTO PLAYER_360.ANALYTIC.daily_active_users AS dau
    USING (
        SELECT
            CAST(LOG_IN AS DATE) AS active_date,
            COUNT(DISTINCT USER_ID) AS active_user_count
        FROM PLAYER_360.RAW.SESSIONS
        WHERE LOG_IN >= CURRENT_DATE - INTERVAL '7 DAY'
        GROUP BY CAST(LOG_IN AS DATE)
    ) AS daily_activity
    ON dau.active_date = daily_activity.active_date
    WHEN MATCHED THEN 
        UPDATE SET dau.active_user_count = daily_activity.active_user_count
    WHEN NOT MATCHED THEN
        INSERT (active_date, active_user_count) 
        VALUES (daily_activity.active_date, daily_activity.active_user_count);

CREATE OR REPLACE TABLE PLAYER_360.ANALYTIC.monthly_active_users (
    active_month DATE,         -- The month for which we are tracking active users (first day of the month)
    active_user_count INT      -- The number of active users in that month
);

-- Insert or update the monthly active users table
MERGE INTO PLAYER_360.ANALYTIC.monthly_active_users AS mau
USING (
    SELECT
        DATE_TRUNC('MONTH', LOG_IN) AS active_month, -- Truncate the LOG_IN date to the first day of the month
        COUNT(DISTINCT USER_ID) AS active_user_count -- Count unique users who logged in that month
    FROM PLAYER_360.RAW.SESSIONS
    --WHERE LOG_IN >= CURRENT_DATE - INTERVAL '12 MONTH' -- Optional: Track the last 12 months (adjust as needed)
    GROUP BY DATE_TRUNC('MONTH', LOG_IN) -- Group by the truncated month
) AS monthly_activity
ON mau.active_month = monthly_activity.active_month
-- If the record exists, update the count of active users, otherwise insert a new record
WHEN MATCHED THEN 
    UPDATE SET mau.active_user_count = monthly_activity.active_user_count
WHEN NOT MATCHED THEN
    INSERT (active_month, active_user_count) 
    VALUES (monthly_activity.active_month, monthly_activity.active_user_count);

CREATE OR REPLACE TASK update_monthly_active_users
  WAREHOUSE = PLAYER_360_BUILD_WH
  SCHEDULE = 'USING CRON 0 0 1 * * UTC' -- Runs on the 1st day of each month at midnight UTC
AS
    MERGE INTO PLAYER_360.ANALYTIC.monthly_active_users AS mau
    USING (
        SELECT
            DATE_TRUNC('MONTH', LOG_IN) AS active_month,
            COUNT(DISTINCT USER_ID) AS active_user_count
        FROM PLAYER_360.RAW.SESSIONS
        WHERE LOG_IN >= CURRENT_DATE - INTERVAL '2 MONTH'
        GROUP BY DATE_TRUNC('MONTH', LOG_IN)
    ) AS monthly_activity
    ON mau.active_month = monthly_activity.active_month
    WHEN MATCHED THEN 
        UPDATE SET mau.active_user_count = monthly_activity.active_user_count
    WHEN NOT MATCHED THEN
        INSERT (active_month, active_user_count) 
        VALUES (monthly_activity.active_month, monthly_activity.active_user_count);

USE ROLE ACCOUNTADMIN;
ALTER TASK update_daily_active_users RESUME;
ALTER TASK update_monthly_active_users RESUME;

USE ROLE SYSADMIN;

CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.ARPDAU AS
SELECT
    dau.ACTIVE_DATE,
    -- Calculate total revenue for the day
    COALESCE(SUM(p.PURCHASE_AMOUNT), 0) AS total_revenue, -- Sum of all purchases for the day
    dau.ACTIVE_USER_COUNT,
    -- Calculate ARPDAU by dividing total revenue by active users
    CASE WHEN dau.ACTIVE_USER_COUNT > 0 THEN
        SUM(p.PURCHASE_AMOUNT) / dau.ACTIVE_USER_COUNT
    ELSE
        0
    END AS arp_dau -- Average revenue per daily active user
FROM
    PLAYER_360.ANALYTIC.DAILY_ACTIVE_USERS dau
LEFT JOIN
    PLAYER_360.RAW.PURCHASES p
    ON CAST(p.TIMESTAMP_OF_PURCHASE AS DATE) = dau.ACTIVE_DATE
GROUP BY
    dau.ACTIVE_DATE, dau.ACTIVE_USER_COUNT
ORDER BY
    dau.ACTIVE_DATE DESC; -- Optional: Sorting by the date in descending order

    
CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.DARPPU AS 
SELECT
    dau.ACTIVE_DATE,
    -- Calculate total revenue from paying users for the day
    COALESCE(SUM(p.PURCHASE_AMOUNT), 0) AS total_revenue_from_paying_users,
    -- Calculate the total number of paying users for the day
    COUNT(DISTINCT p.USER_ID) AS total_paying_users,
    -- Calculate DARPPU by dividing the total revenue by the number of paying users
    CASE WHEN COUNT(DISTINCT p.USER_ID) > 0 THEN
        SUM(p.PURCHASE_AMOUNT) / COUNT(DISTINCT p.USER_ID)
    ELSE
        0
    END AS darppu
FROM
    PLAYER_360.ANALYTIC.DAILY_ACTIVE_USERS dau
LEFT JOIN
    PLAYER_360.RAW.PURCHASES p
    ON CAST(p.TIMESTAMP_OF_PURCHASE AS DATE) = dau.ACTIVE_DATE
    AND p.PURCHASE_TYPE != 'none' 
GROUP BY
    dau.ACTIVE_DATE
ORDER BY
    dau.ACTIVE_DATE DESC;

CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.MONTHLY_CHURN_RATE AS
WITH ActiveUsers AS (
    -- Get all active users per month
    SELECT 
        EXTRACT(YEAR, LOG_IN) AS year,
        EXTRACT(MONTH, LOG_IN) AS month,
        USER_ID
    FROM PLAYER_360.RAW.SESSIONS
    GROUP BY EXTRACT(YEAR, LOG_IN), EXTRACT(MONTH, LOG_IN), USER_ID
),
ChurnedUsers AS (
    -- Get churned users by comparing active users in consecutive months
    SELECT 
        a.year AS year,
        a.month AS month,
        a.USER_ID
    FROM ActiveUsers a
    LEFT JOIN ActiveUsers b
        ON a.USER_ID = b.USER_ID
        AND a.year = b.year
        AND a.month = b.month + 1 -- Compare current month to previous month
    WHERE b.USER_ID IS NULL  -- Users active in previous month but not current month (churned)
),
MonthlyStats AS (
    -- Aggregate counts of active and churned users per month
    SELECT
        a.year,
        a.month,
        COUNT(DISTINCT a.USER_ID) AS active_users,
        COUNT(DISTINCT c.USER_ID) AS churned_users
    FROM ActiveUsers a
    LEFT JOIN ChurnedUsers c
        ON a.USER_ID = c.USER_ID
        AND a.year = c.year
        AND a.month = c.month
    GROUP BY a.year, a.month
),
EarliestMonth AS (
    -- Find the first month of the earliest year in the dataset
    SELECT MIN(year) AS earliest_year, MIN(month) AS earliest_month
    FROM ActiveUsers
),
FilteredMonthlyStats AS (
    -- Filter out the first month of the earliest year
    SELECT 
        ms.year,
        ms.month,
        ms.churned_users,
        ms.active_users,
        CASE 
            WHEN ms.active_users > 0 THEN (ms.churned_users::FLOAT / ms.active_users::FLOAT) * 100
            ELSE NULL
        END AS churn_rate_percentage
    FROM MonthlyStats ms
    JOIN EarliestMonth em
        ON NOT (ms.year = em.earliest_year AND ms.month = em.earliest_month) -- Exclude the first month of the earliest year
)
SELECT * 
FROM FilteredMonthlyStats
ORDER BY year, month;

CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.DAILY_CHURN_RATE AS
WITH ActiveUsers AS (
    -- Get all active users per day
    SELECT 
        DATE(LOG_IN) AS log_in_date,
        USER_ID
    FROM PLAYER_360.RAW.SESSIONS
    GROUP BY DATE(LOG_IN), USER_ID
),
ChurnedUsers AS (
    -- Get churned users by comparing active users on consecutive days using LAG function
    SELECT 
        a.USER_ID,
        a.log_in_date
    FROM ActiveUsers a
    LEFT JOIN ActiveUsers b
        ON a.USER_ID = b.USER_ID
        AND b.log_in_date = DATEADD(DAY, -1, a.log_in_date)  -- Compare previous day's log_in_date
    WHERE b.USER_ID IS NULL  -- Users active on the previous day but not on current day (churned)
),
DailyStats AS (
    -- Aggregate counts of active and churned users per day
    SELECT
        a.log_in_date,
        COUNT(DISTINCT a.USER_ID) AS active_users,
        COUNT(DISTINCT c.USER_ID) AS churned_users
    FROM ActiveUsers a
    LEFT JOIN ChurnedUsers c
        ON a.USER_ID = c.USER_ID
        AND a.log_in_date = c.log_in_date
    GROUP BY a.log_in_date
),
EarliestDate AS (
    -- Find the earliest date (the first active day)
    SELECT MIN(DATE(LOG_IN)) AS earliest_date
    FROM PLAYER_360.RAW.SESSIONS
),
FilteredDailyStats AS (
    -- Filter out the first active day
    SELECT 
        ds.log_in_date,
        ds.churned_users,
        ds.active_users,
        CASE 
            WHEN ds.active_users > 0 THEN (ds.churned_users::FLOAT / ds.active_users::FLOAT) * 100
            ELSE NULL
        END AS churn_rate_percentage
    FROM DailyStats ds
    JOIN EarliestDate ed
        ON ds.log_in_date != ed.earliest_date  -- Exclude the first active day
)
SELECT 
    log_in_date,
    churned_users,
    active_users,
    churn_rate_percentage
FROM FilteredDailyStats
ORDER BY log_in_date;

CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.COHORT_CLTV AS
WITH CohortData AS (
    -- Step 1: Assign players to cohorts based on the month of account creation
    SELECT
        u.USER_ID,
        -- Create a cohort label based on account creation date (monthly cohort)
        TO_CHAR(u.ACCOUNT_CREATION, 'YYYY-MM') AS CohortMonth,
        p.PURCHASE_AMOUNT,
        p.TIMESTAMP_OF_PURCHASE,
        u.ACCOUNT_CREATION
    FROM
        PLAYER_360.RAW.USERS u
    LEFT JOIN
        PLAYER_360.RAW.PURCHASES p
    ON
        u.USER_ID = p.USER_ID
    WHERE
        u.CONSENT = TRUE -- Filter out users who haven't consented, if applicable
),

CohortRevenue AS (
    -- Step 2: Sum the total revenue for each cohort
    SELECT
        CohortMonth,
        SUM(PURCHASE_AMOUNT) AS TotalRevenue,
        COUNT(DISTINCT USER_ID) AS TotalPlayers,
        MIN(ACCOUNT_CREATION) AS CohortStartDate -- The first account creation date in the cohort
    FROM
        CohortData
    GROUP BY
        CohortMonth
),

CohortLTV AS (
    -- Step 3: Calculate LTV for each cohort
    SELECT
        CohortMonth,
        TotalRevenue,
        TotalPlayers,
        (TotalRevenue / TotalPlayers) AS LTV,
        CohortStartDate
    FROM
        CohortRevenue
),

CohortNormalizedLTV AS (
    -- Step 4: Calculate Normalized LTV
    SELECT
        CohortMonth,
        TotalRevenue,
        TotalPlayers,
        LTV,
        CohortStartDate,
        -- Calculate the number of months from Cohort Start Date to Today
        MONTHS_BETWEEN(CURRENT_DATE, CohortStartDate) AS MonthsActive,
        -- Normalize the LTV by dividing by the number of months active
        (TotalRevenue / NULLIF(MONTHS_BETWEEN(CURRENT_DATE, CohortStartDate), 0)) AS NormalizedLTV
    FROM
        CohortLTV
)

-- Final Result: Display Cohort LTV, Normalized LTV, and other details
SELECT
    CohortMonth as Cohort_Month,
    TotalRevenue as Total_Revenue,
    TotalPlayers as Total_Players,
    LTV,
    MonthsActive as Months_Active,
    NormalizedLTV as Normalized_LTV
FROM
    CohortNormalizedLTV
ORDER BY
    CohortMonth;

WITH AdViewers AS (
    -- Step 1: Identify users who have interacted with ads, grouped by ad type
    SELECT DISTINCT USER_ID, AD_TYPE
    FROM PLAYER_360.RAW.PURCHASES p
    WHERE p.AD_INTERACTION_ID IS NOT NULL
),
AdConverters AS (
    -- Step 2: Identify users who interacted with ads and made a purchase, grouped by ad type
    SELECT DISTINCT p.USER_ID, p.AD_TYPE
    FROM PLAYER_360.RAW.PURCHASES p
    WHERE p.AD_INTERACTION_ID IS NOT NULL AND p.PURCHASE_TYPE != 'none'
)

-- Step 3: Calculate purchase conversion rate by ad type
SELECT
    av.AD_TYPE,
    COUNT(DISTINCT u.user_id) AS TOTAL_USERS,
    COUNT(DISTINCT av.USER_ID) AS TotalUsersWhoInteractedWithAds,
    COUNT(DISTINCT ac.USER_ID) AS NumberOfPayingUsers,
    (COUNT(DISTINCT ac.USER_ID) * 100.0 / COUNT(DISTINCT av.USER_ID)) AS PurchaseConversionRate,
FROM
    AdViewers av
LEFT JOIN
    AdConverters ac ON av.USER_ID = ac.USER_ID AND av.AD_TYPE = ac.AD_TYPE
LEFT JOIN
    PLAYER_360.RAW.USERS u
GROUP BY
    av.AD_TYPE
ORDER BY
    PurchaseConversionRate DESC;
    
-- NExt
CREATE OR REPLACE VIEW PLAYER_360.ANALYTIC.AD_CONVERSION_OVER_TIME AS
SELECT
    TO_CHAR(p.TIMESTAMP_OF_PURCHASE, 'YYYY-MM') AS Month,  -- Extract month and year in 'YYYY-MM' format
    p.AD_TYPE,
    COUNT(p.AD_INTERACTION_ID) AS Total_Ads, 
    COUNT(DISTINCT CASE WHEN p.PURCHASE_TYPE != 'none' THEN p.PURCHASE_ID END) AS PURCHASED_ADS,
    (COUNT(DISTINCT CASE WHEN p.PURCHASE_TYPE != 'none' THEN p.PURCHASE_ID END) * 1.0 / COUNT(p.AD_INTERACTION_ID)) AS Ad_Conversion_Rate
FROM
    PLAYER_360.RAW.PURCHASES p
GROUP BY
    TO_CHAR(p.TIMESTAMP_OF_PURCHASE, 'YYYY-MM'),  -- Group by month and year
    p.AD_TYPE
ORDER BY
    Month DESC, p.ad_type DESC;