#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

if [ "${LOAD_STUDY_ASSETS:-1}" = "1" ]; then
    echo "Synchronising study assets..."
    python manage.py insert_assets
fi

exec "$@"

