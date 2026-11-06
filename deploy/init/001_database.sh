#!/usr/bin/env bash
set -Eeuo pipefail
# Passwords are read by psql from secret files, never placed in command arguments.
export ECI_PIPELINE_PASSWORD="$(cat /run/secrets/pipeline_password)"
export ECI_READER_PASSWORD="$(cat /run/secrets/reader_password)"
psql -X -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<'SQL'
\getenv pipeline_password ECI_PIPELINE_PASSWORD
CREATE ROLE complaints_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pipeline_password';
CREATE DATABASE ecommerce_complaints OWNER complaints_user;
SQL
psql -X -v ON_ERROR_STOP=1 --username postgres --dbname ecommerce_complaints <<'SQL'
SET ROLE complaints_user;
\i /opt/eci-sql/init_database.sql
RESET ROLE;
\i /opt/eci-sql/analytics/create_dashboard_reader.sql
\getenv reader_password ECI_READER_PASSWORD
ALTER ROLE complaints_dashboard PASSWORD :'reader_password';
SQL
unset ECI_PIPELINE_PASSWORD ECI_READER_PASSWORD
