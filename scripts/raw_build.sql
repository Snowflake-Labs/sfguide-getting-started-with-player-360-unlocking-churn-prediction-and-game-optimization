USE ROLE SYSADMIN;
USE SCHEMA PLAYER_360.RAW;
USE WAREHOUSE PLAYER_360_BUILD_WH;

CREATE OR REPLACE FILE FORMAT json_format
    TYPE = json
    COMPRESSION = GZIP
    STRIP_OUTER_ARRAY =TRUE;

CREATE OR REPLACE FILE FORMAT csv_format
    TYPE = csv
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    PARSE_HEADER = TRUE;

CREATE OR REPLACE FILE FORMAT csv_gz_format
  TYPE = csv
  COMPRESSION = GZIP
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  PARSE_HEADER = TRUE;
    
create or replace TABLE PLAYER_360.RAW.USERS 
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/users.csv',
          FILE_FORMAT=>'csv_format',
          IGNORE_CASE => TRUE
        )
    ));
    
create or replace TABLE PLAYER_360.RAW.ACHIEVEMENTS 
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/users_achievement_final.csv',
          FILE_FORMAT=>'csv_format',
          IGNORE_CASE => TRUE
        )
    ));

create or replace TABLE PLAYER_360.RAW.PURCHASES
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/purchases_output/',
          FILE_FORMAT=>'csv_gz_format',
          IGNORE_CASE => TRUE
        )
    ));

create or replace TABLE PLAYER_360.RAW.SESSIONS
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/sessions_output',
          FILE_FORMAT=>'csv_gz_format',
          IGNORE_CASE => TRUE
        )
    ));
    
create or replace TABLE PLAYER_360.RAW.GAME_EVENTS
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/game_events_output',
          FILE_FORMAT=>'json_format',
          IGNORE_CASE => TRUE
        )
    ));

create or replace TABLE PLAYER_360.RAW.SUPPORT_TICKETS
USING TEMPLATE (
	SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*))
    WITHIN GROUP (ORDER BY order_id)
      FROM TABLE(
        INFER_SCHEMA(
          LOCATION=>'@SUPPORT/support_tickets.csv',
          FILE_FORMAT=>'csv_format',
          IGNORE_CASE => TRUE
        )
    ));

COPY INTO PLAYER_360.RAW.USERS 
FROM @PLAYER_360.RAW.SUPPORT/users.csv 
FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

COPY INTO PLAYER_360.RAW.ACHIEVEMENTS 
FROM @PLAYER_360.RAW.SUPPORT/users_achievement_final.csv 
FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

COPY INTO PLAYER_360.RAW.PURCHASES 
FROM @PLAYER_360.RAW.SUPPORT/purchases_output/
FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

COPY INTO PLAYER_360.RAW.SESSIONS 
FROM @PLAYER_360.RAW.SUPPORT/sessions_output/
FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

COPY INTO PLAYER_360.RAW.GAME_EVENTS 
FROM @PLAYER_360.RAW.SUPPORT/game_events_output/
FILE_FORMAT = 'json_format'
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;

COPY INTO PLAYER_360.RAW.SUPPORT_TICKETS
FROM @PLAYER_360.RAW.SUPPORT/support_tickets.csv 
FILE_FORMAT = (TYPE = 'CSV', SKIP_HEADER = 1);

-- Assign the value of DATEDIFF to the variable
SET days_since_max_log_out = (
    SELECT DATEDIFF(day, CURRENT_DATE, MAX(LOG_OUT)) 
    FROM PLAYER_360.RAW.SESSIONS
);

-- Update the days
UPDATE PLAYER_360.RAW.SESSIONS s
SET 
    LOG_IN = DATEADD(DAY, (SELECT $days_since_max_log_out), s.LOG_IN),
    LOG_OUT = DATEADD(DAY, (SELECT $days_since_max_log_out), s.LOG_OUT);

UPDATE PLAYER_360.RAW.PURCHASES p
SET TIMESTAMP_OF_PURCHASE = DATEADD(DAY, (SELECT $days_since_max_log_out), p.TIMESTAMP_OF_PURCHASE);
