-- Databases and schemas required by the POC.
-- Applied first (files run in lexical order), so table DDL can be fully qualified.

CREATE DATABASE IF NOT EXISTS PROD;
CREATE SCHEMA IF NOT EXISTS PROD.DS_MODEL;
