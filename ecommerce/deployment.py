"""
Helpers for running StarEastStore on a PaaS platform (Render, Railway, Fly...).

Platforms inject environment variables that describe the public hostname of the
running service.  Render, for example, sets ``RENDER_EXTERNAL_HOSTNAME`` (the
service's ``*.onrender.com`` hostname) and ``RENDER_EXTERNAL_URL`` (its full
public URL).

Django answers **400 Bad Request** (``DisallowedHost``) for any request whose
``Host`` header is missing from ``ALLOWED_HOSTS``.  Because that check runs
before URL resolution, *every* path on the site - the homepage, ``/health/``,
``/static/...`` - fails at once and the deployment looks completely broken.
The hostname only exists after the service has been created, so it is easy to
leave ``ALLOWED_HOSTS`` stale.  The helpers below read it from the platform's
own environment variables so :mod:`ecommerce.settings` can allow it
automatically, while still honouring explicitly configured values.
"""
from __future__ import annotations

from urllib.parse import urlparse

RENDER_EXTERNAL_HOSTNAME_ENV = 'RENDER_EXTERNAL_HOSTNAME'
RENDER_EXTERNAL_URL_ENV = 'RENDER_EXTERNAL_URL'

_TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def as_bool(value: object) -> bool:
    """Interpret an env-var style value as a boolean ('1', 'true', 'yes', 'on')."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE_VALUES


def clean(value: object) -> str:
    """Normalise an environment value to a stripped string ('' when unset)."""
    if value is None:
        return ''
    return str(value).strip()


def hostname_from_url(url: str) -> str:
    """Return the hostname of *url* ('' when it is missing or unparsable)."""
    url = clean(url)
    if not url:
        return ''
    try:
        parsed = urlparse(url)
    except ValueError:
        return ''
    return clean(parsed.hostname).lower()


def merge_unique(*sequences) -> list[str]:
    """Concatenate sequences, dropping empty values and duplicates (stable order)."""
    merged: list[str] = []
    for sequence in sequences:
        for item in sequence or ():
            value = clean(item)
            if value and value not in merged:
                merged.append(value)
    return merged


def running_on_render(environ) -> bool:
    """True when this process runs on Render (it exports ``RENDER=true``)."""
    return (
        as_bool(environ.get('RENDER'))
        or bool(clean(environ.get(RENDER_EXTERNAL_HOSTNAME_ENV)))
        or bool(clean(environ.get(RENDER_EXTERNAL_URL_ENV)))
    )


def platform_hostnames(environ) -> list[str]:
    """Hostnames the platform says this service is reachable at."""
    hostname = clean(environ.get(RENDER_EXTERNAL_HOSTNAME_ENV)).lower()
    return merge_unique(
        [hostname],
        [hostname_from_url(environ.get(RENDER_EXTERNAL_URL_ENV))],
    )


def platform_origins(environ, scheme: str = 'https') -> list[str]:
    """Origins (``scheme://host``) the platform serves this service from."""
    origins = [f'{scheme}://{host}' for host in platform_hostnames(environ)]
    url = clean(environ.get(RENDER_EXTERNAL_URL_ENV))
    if url:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            # Keep the platform's own scheme (Render always reports https).
            origins.append(f'{parsed.scheme}://{parsed.netloc}')
    return merge_unique(origins)
