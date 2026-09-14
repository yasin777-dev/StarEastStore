"""Shared utilities: rate limiting and misc helpers."""
from __future__ import annotations

import time

from django.core.cache import cache
from django.http import HttpResponse


def client_ip(request) -> str:
    """Best-effort client IP (respects the common X-Forwarded-For header)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def rate_limit(key_prefix: str, limit: int = 10, per_seconds: int = 60):
    """
    Simple cache-based rate limiter for sensitive POST endpoints.

    Usage:
        @method_decorator(rate_limit('login', limit=8, per_seconds=60), name='post')
    Returns HTTP 429 when the calling IP exceeds ``limit`` requests within
    ``per_seconds``. Good enough for dev/small deployments; swap for a
    distributed limiter (e.g. Redis based) at scale.
    """
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if request.method != 'POST':
                return view_func(request, *args, **kwargs)
            cache_key = f'rl:{key_prefix}:{client_ip(request)}'
            # A small sorted list of timestamps in the cache.
            hits = cache.get(cache_key) or []
            now = time.monotonic()
            hits = [ts for ts in hits if now - ts < per_seconds]
            if len(hits) >= limit:
                return HttpResponse(
                    'Too many attempts. Please try again in a minute.',
                    status=429,
                )
            hits.append(now)
            cache.set(cache_key, hits, per_seconds)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
