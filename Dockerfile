# StarEastStore - production image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 (wheels cover most; build tools as fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system django && adduser --system --ingroup django django \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app/media /app/staticfiles
USER django

RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

CMD ["gunicorn", "ecommerce.wsgi:application", "--config", "gunicorn.conf.py"]
