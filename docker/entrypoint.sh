#!/bin/sh
set -eu

mkdir -p "${DATA_DIR:-/data/videos}"
cd /app
PYTHONPATH=src alembic upgrade head
exec supervisord -n -c /etc/supervisor/supervisord.conf
