FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Run migrations, start bot in background, then start gunicorn
CMD ["sh", "-c", "python manage.py migrate && python manage.py runbot & gunicorn eventometer.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2"]
