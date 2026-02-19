#!/bin/sh
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput 2>/dev/null || true

echo "=== Starting Discord bot in background ==="
python manage.py runbot &

echo "=== Starting Gunicorn web server on port ${PORT:-8000} ==="
exec gunicorn eventometer.wsgi \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
