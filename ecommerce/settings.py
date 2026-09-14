"""
Django settings for the StarEastStore e-commerce project.

All deployment-specific configuration is read from environment variables
(a ``.env`` file is loaded automatically via python-dotenv).  Safe defaults
are provided for local development; production values should always come
from the environment.  See ``.env.example`` for the full list.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, unquote

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & environment
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env(key: str, default: str = '') -> str:
    """Read a string environment variable."""
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean environment variable ('1', 'true', 'yes', 'on')."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_int(key: str, default: int = 0) -> int:
    """Read an integer environment variable."""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def env_decimal(key: str, default: str = '0') -> Decimal:
    """Read a decimal environment variable (used for tax rates etc.)."""
    try:
        return Decimal(os.environ.get(key, default))
    except Exception:
        return Decimal(default)


def env_list(key: str, default: list[str] | None = None) -> list[str]:
    """Read a comma-separated environment variable into a list."""
    raw = os.environ.get(key)
    if raw is None:
        return default if default is not None else []
    return [item.strip() for item in raw.split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env(
    'SECRET_KEY',
    'django-insecure-dev-only-key-#change-me-in-production-0x4f2a',
)

DEBUG = env_bool('DEBUG', True)

if DEBUG:
    ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['*'])
else:
    ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1'])

CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    ['http://localhost:8000', 'http://127.0.0.1:8000'],
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Third party
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    # Local apps
    'core',
    'accounts',
    'products',
    'cart',
    'orders',
    'payments',
    'reviews',
    'wishlist',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ecommerce.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.shop_settings',
                'cart.context_processors.cart_summary',
            ],
        },
    },
]

WSGI_APPLICATION = 'ecommerce.wsgi.application'
ASGI_APPLICATION = 'ecommerce.asgi.application'


# ---------------------------------------------------------------------------
# Database - PostgreSQL in production, SQLite fallback for development
# ---------------------------------------------------------------------------
def _parse_database_url(url: str) -> dict:
    """Minimal DATABASE_URL parser (no external dependency required)."""
    parsed = urlparse(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError(f'Unsupported DATABASE_URL scheme: {parsed.scheme!r}')
    sslmode = dict(parse_qsl(parsed.query)).get('sslmode')
    db: dict = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')) or 'ecommerce',
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or 'localhost',
        'PORT': parsed.port or 5432,
        'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 60),
    }
    if sslmode:
        db['OPTIONS'] = {'sslmode': sslmode}
    return db


_DATABASE_URL = env('DATABASE_URL')
if _DATABASE_URL:
    DATABASES = {'default': _parse_database_url(_DATABASE_URL)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / env('SQLITE_NAME', 'db.sqlite3'),
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['accounts.backends.EmailBackend']

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:home'
LOGOUT_REDIRECT_URL = 'core:home'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = env('LANGUAGE_CODE', 'en-us')
TIME_ZONE = env('TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise: compressed storage by default.  Enable the manifest finder in
# production (after ``collectstatic``) with STATIC_MANIFEST=True.
if env_bool('STATIC_MANIFEST', False):
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }

# Maximum upload size for product/profile images (bytes).
MAX_IMAGE_UPLOAD_SIZE = env_int('MAX_IMAGE_UPLOAD_SIZE', 5 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}


# ---------------------------------------------------------------------------
# Email (configurable through environment variables)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'StarEastStore <no-reply@stareaststore.example.com>')
ADMIN_EMAIL_NOTIFICATIONS = env_list('ADMIN_EMAIL_NOTIFICATIONS', ['orders@stareaststore.example.com'])
PASSWORD_RESET_TIMEOUT = env_int('PASSWORD_RESET_TIMEOUT', 60 * 60 * 24)  # 24h


# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': env_int('API_PAGE_SIZE', 12),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': env('API_ANON_THROTTLE', '200/hour'),
        'user': env('API_USER_THROTTLE', '600/hour'),
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}


# ---------------------------------------------------------------------------
# Shop business rules (all totals are computed on the backend)
# ---------------------------------------------------------------------------
CURRENCY = env('CURRENCY', '$')
SHOP_NAME = env('SHOP_NAME', 'StarEastStore')
SHOP_TAGLINE = env('SHOP_TAGLINE', 'Everything under the eastern stars')

# Order-level tax applied to (subtotal - discount). Set e.g. 0.08 for 8% VAT.
TAX_RATE = env_decimal('TAX_RATE', '0.00')
# Subtotal (after discount) above which shipping is free.
FREE_SHIPPING_THRESHOLD = env_decimal('FREE_SHIPPING_THRESHOLD', '75')

# Session key for the guest cart.
CART_SESSION_KEY = 'cart_items'
# Checkout allows at most this many units of a line item.
MAX_LINE_QUANTITY = env_int('MAX_LINE_QUANTITY', 99)

LOW_STOCK_ALERT_QUANTITY = env_int('LOW_STOCK_ALERT_QUANTITY', 5)


# ---------------------------------------------------------------------------
# Payment gateways
# ---------------------------------------------------------------------------
PAYMENT_SETTINGS = {
    'STRIPE_SECRET_KEY': env('STRIPE_SECRET_KEY'),
    'STRIPE_PUBLISHABLE_KEY': env('STRIPE_PUBLISHABLE_KEY'),
    'STRIPE_WEBHOOK_SECRET': env('STRIPE_WEBHOOK_SECRET'),
    'RAZORPAY_KEY_ID': env('RAZORPAY_KEY_ID'),
    'RAZORPAY_KEY_SECRET': env('RAZORPAY_KEY_SECRET'),
    'RAZORPAY_WEBHOOK_SECRET': env('RAZORPAY_WEBHOOK_SECRET'),
}
# The simulated gateway is handy for development and demos; keep it disabled
# in production unless you really know what you are doing.
SIMULATED_GATEWAY_ENABLED = env_bool('SIMULATED_GATEWAY_ENABLED', DEBUG)


# ---------------------------------------------------------------------------
# Security (hardened automatically when DEBUG=False; see README for HTTPS)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

    if env_bool('SECURE_SSL_REDIRECT', False):
        SECURE_SSL_REDIRECT = True
    if env_bool('BEHIND_PROXY', False):
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    if env_bool('SECURE_HSTS', True):
        SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 31536000)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
    if env_bool('SECURE_COOKIES', True):
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True


# ---------------------------------------------------------------------------
# Logging (console only; never print secrets)
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {name} {asctime} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {'handlers': ['console'], 'level': env('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django': {'level': 'INFO', 'propagate': True},
        'ecommerce': {'level': env('LOG_LEVEL', 'INFO'), 'propagate': True},
    },
}
