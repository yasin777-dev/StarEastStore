#!/usr/bin/env bash
# Build script used by PaaS platforms (Render runs this as the "build command")
# and handy locally / in CI. It only performs idempotent steps.
set -o errexit

pip install -r requirements.txt

# Collect everything WhiteNoise serves in production (STATIC_ROOT).
# Set STATIC_MANIFEST=True to also hash the filenames for long-term caching.
python manage.py collectstatic --no-input

# Apply database migrations. gunicorn.conf.py repeats this at boot on platforms
# whose build environment cannot reach the database (harmless when already up
# to date).
python manage.py migrate --noinput
