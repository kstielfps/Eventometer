FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Collect static files (may fail without env vars, that's ok)
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE ${PORT:-8000}

CMD ["./start.sh"]
