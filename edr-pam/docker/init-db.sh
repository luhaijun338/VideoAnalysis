#!/bin/sh
set -eu

until pg_isready -h video-analysis-db -U va -d postgres >/dev/null 2>&1; do
  echo "waiting for postgres..."
  sleep 1
done

exists=$(PGPASSWORD=va psql -h video-analysis-db -U va -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='edr_pam'")
if [ "$exists" != "1" ]; then
  PGPASSWORD=va psql -h video-analysis-db -U va -d postgres -c "CREATE DATABASE edr_pam;"
  echo "created database edr_pam"
else
  echo "database edr_pam already exists"
fi
