#!/bin/sh
set -e

DB_PATH="${DATABASE_PATH:-/data/budget.sqlite3}"
mkdir -p "$(dirname "$DB_PATH")"

echo "Applying database migrations..."
alembic upgrade head

exec "$@"
