web: python manage.py migrate && gunicorn eventometer.wsgi --bind 0.0.0.0:$PORT --workers 2
bot: python manage.py runbot
