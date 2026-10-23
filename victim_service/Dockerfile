FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home app && mkdir -p /app/logs && chown -R app /app
USER app

EXPOSE 8001
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_activity && gunicorn victim_project.wsgi:application --bind 0.0.0.0:8001 --workers 2 --threads 32 --timeout 30"]
