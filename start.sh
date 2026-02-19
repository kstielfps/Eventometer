#!/bin/sh
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput 2>/dev/null || true

echo "=== Creating superuser (if not exists) ==="
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eventometer.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
if password and not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f'Superuser \"{username}\" created.')
else:
    print(f'Superuser \"{username}\" already exists or no password set. Skipping.')
"

echo "=== Starting Discord bot in background ==="
python manage.py runbot &

echo "=== Starting Gunicorn web server on port ${PORT:-8000} ==="
exec gunicorn eventometer.wsgi \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
