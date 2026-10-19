#!/bin/bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE video_analysis_test;
    CREATE DATABASE edr_pam;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname video_analysis_test <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
