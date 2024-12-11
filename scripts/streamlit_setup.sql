use role SYSADMIN;
CREATE OR REPLACE STREAMLIT PLAYER_360.APP.PLAYER_360_streamlit
ROOT_LOCATION = '@PLAYER_360.APP.streamlit_player360'
MAIN_FILE = 'PLAYER_360.py'
QUERY_WAREHOUSE = 'PLAYER_360_DATA_APP_WH'
COMMENT = '{"origin":"sf_sit-is","name":"player_360","version":{"major":1, "minor":0},"attributes":{"is_quickstart":1, "source":"streamlit"}}';