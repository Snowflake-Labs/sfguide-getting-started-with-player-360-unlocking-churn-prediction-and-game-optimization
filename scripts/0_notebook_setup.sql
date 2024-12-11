use role SYSADMIN;
CREATE OR REPLACE NOTEBOOK PLAYER_360.ANALYTIC.PLAYER_360_static_churn_prediction
FROM '@PLAYER_360.ANALYTIC.notebook_static_churn_prediction'
MAIN_FILE = 'Static_Churn_Prediction_Model.ipynb'
QUERY_WAREHOUSE = 'PLAYER_360_DS_WH';