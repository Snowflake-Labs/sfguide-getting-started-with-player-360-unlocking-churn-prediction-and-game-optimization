use role SYSADMIN;
CREATE OR REPLACE NOTEBOOK PLAYER_360.ANALYTIC.PLAYER_360_static_churn_prediction
FROM '@PLAYER_360.ANALYTIC.notebook_static_churn_prediction'
MAIN_FILE = '0_start_here.ipynb'
QUERY_WAREHOUSE = 'PLAYER_360_DATA_APP_WH';