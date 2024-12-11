ALTER SESSION SET query_tag = '{"origin":"sf_sit-is", "name":"Player_360", "version":{"major":1, "minor":0}, "attributes":{"is_quickstart":1, "source":"sql"}}';
USE ROLE accountadmin;
USE DATABASE PLAYER_360;
USE SCHEMA ANALYTIC;

-- Create and grant access to compute pools
CREATE COMPUTE POOL IF NOT EXISTS PLAYER_360_cpu_xs_5_nodes
  MIN_NODES = 1
  MAX_NODES = 5
  INSTANCE_FAMILY = CPU_X64_XS;

CREATE COMPUTE POOL IF NOT EXISTS PLAYER_360_gpu_s_5_nodes
  MIN_NODES = 1
  MAX_NODES = 5
  INSTANCE_FAMILY = GPU_NV_S;

GRANT USAGE ON COMPUTE POOL PLAYER_360_cpu_xs_5_nodes TO ROLE PLAYER_360_DATA_SCIENTIST;
GRANT USAGE ON COMPUTE POOL PLAYER_360_gpu_s_5_nodes TO ROLE PLAYER_360_DATA_SCIENTIST;

-- Create and grant access to EAIs
-- Substep #1: create network rules (these are schema-level objects; end users do not need direct access to the network rules)

create or replace network rule PLAYER_360_allow_all_rule
  TYPE = 'HOST_PORT'
  MODE= 'EGRESS'
  VALUE_LIST = ('0.0.0.0:443','0.0.0.0:80');

-- Substep #2: create external access integration (these are account-level objects; end users need access to this to access the public internet with endpoints defined in network rules)

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION PLAYER_360_allow_all_integration
  ALLOWED_NETWORK_RULES = (PLAYER_360_allow_all_rule)
  ENABLED = true;

CREATE OR REPLACE NETWORK RULE PLAYER_360_pypi_network_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('pypi.org', 'pypi.python.org', 'pythonhosted.org',  'files.pythonhosted.org');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION PLAYER_360_pypi_access_integration
  ALLOWED_NETWORK_RULES = (PLAYER_360_pypi_network_rule)
  ENABLED = true;

GRANT ALL PRIVILEGES ON INTEGRATION PLAYER_360_allow_all_integration TO ROLE SYSADMIN;
GRANT ALL PRIVILEGES ON INTEGRATION PLAYER_360_pypi_access_integration TO ROLE SYSADMIN;


USE ROLE PLAYER_360_DATA_SCIENTIST;
USE WAREHOUSE PLAYER_360_DS_WH;
USE DATABASE PLAYER_360;
USE SCHEMA ANALYTIC;

CREATE OR REPLACE NOTEBOOK PLAYER_360.ANALYTIC.PLAYER_360_rolling_churn_prediction
FROM '@PLAYER_360.ANALYTIC.notebook_rolling_churn_prediction'
MAIN_FILE = 'Rolling_Churn_Prediction_Model.ipynb'
QUERY_WAREHOUSE = 'PLAYER_360_DS_WH'
COMPUTE_POOL='PLAYER_360_gpu_s_5_nodes'
RUNTIME_NAME='SYSTEM$GPU_RUNTIME';
ALTER NOTEBOOK PLAYER_360_rolling_churn_prediction ADD LIVE VERSION FROM LAST;
ALTER NOTEBOOK PLAYER_360_rolling_churn_prediction set external_access_integrations = ("PLAYER_360_pypi_access_integration", 
                                                                                                            "PLAYER_360_allow_all_integration");