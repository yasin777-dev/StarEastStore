"""Gunicorn configuration for StarEastStore (tune workers for your host).

Works for bare metal / Docker *and* for PaaS platforms that inject a ``PORT``
environment variable (Render, Heroku, Fly...).  On platforms where a service is
expected to bootstrap itself, the server also applies pending migrations and
collects static files once, before the workers start.
"""
import multiprocessing
import os
import sys

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _default_bind() -> str:
    """Bind address: GUNICORN_BIND wins, then the platform's PORT, else 8000."""
    explicit = (os.environ.get('GUNICORN_BIND') or '').strip()
    if explicit:
        return explicit
    port = (os.environ.get('PORT') or '').strip()
    if port:
        # PaaS platforms route traffic to $PORT (Render defaults to 10000).  The
        # Docker image additionally publishes 8000, so listen on both whenever
        # they differ - that keeps native and Docker deploys working unchanged.
        return '0.0.0.0:8000' if port == '8000' else f'0.0.0.0:{port},0.0.0.0:8000'
    return '0.0.0.0:8000'


bind = _default_bind()

# WEB_CONCURRENCY is the de-facto platform convention (Render sets it); cap the
# auto-detected default so a many-core host does not spawn dozens of workers in
# a small (512 MB) container and get OOM-killed.
workers = int(
    os.environ.get('GUNICORN_WORKERS')
    or os.environ.get('WEB_CONCURRENCY')
    or min(multiprocessing.cpu_count() * 2 + 1, 4)
)
worker_class = 'sync'
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')


# ---------------------------------------------------------------------------
# Deploy bootstrap (idempotent, runs once in the master before workers fork)
# ---------------------------------------------------------------------------
# Enabled automatically when the process runs on Render, where a deploy cannot
# otherwise be relied on to have applied migrations / collected static files.
# Every step can be switched off: AUTO_MIGRATE=False, AUTO_COLLECTSTATIC=False.
ON_RENDER = bool(os.environ.get('RENDER')) or bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME'))
AUTO_MIGRATE = _env_bool('AUTO_MIGRATE', ON_RENDER)
AUTO_COLLECTSTATIC = _env_bool('AUTO_COLLECTSTATIC', ON_RENDER)


def _bootstrap_log(message: str) -> None:
    print(f'[bootstrap] {message}', file=sys.stderr, flush=True)


def on_starting(server):  # noqa: ARG001 - gunicorn hook signature
    """Apply pending migrations and collect static files before serving."""
    if not (AUTO_MIGRATE or AUTO_COLLECTSTATIC):
        return

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
    try:
        import django

        django.setup()
        from django.core.management import call_command
    except Exception as exc:  # pragma: no cover - configuration error
        _bootstrap_log(f'could not import Django ({exc}); skipping bootstrap')
        return

    if AUTO_MIGRATE:
        try:
            call_command('migrate', interactive=False, verbosity=1)
            _bootstrap_log('database migrations applied')
        except Exception as exc:
            # Never crash-loop the service on a bootstrap hiccup: log loudly and
            # start anyway (/health/ reports the database state).
            _bootstrap_log(f'database migration failed: {exc}')

    if AUTO_COLLECTSTATIC:
        try:
            call_command('collectstatic', interactive=False, verbosity=0)
            _bootstrap_log('static files collected')
        except Exception as exc:
            _bootstrap_log(f'collectstatic failed: {exc}')
