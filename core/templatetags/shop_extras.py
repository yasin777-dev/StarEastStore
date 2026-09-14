"""Template helpers used across the storefront templates."""
from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dictionary/attribute lookup by variable key: {{ mapping|get_item:key }}."""
    if mapping is None:
        return 0
    try:
        return mapping.get(key, 0)
    except AttributeError:
        return 0


@register.filter
def stars(full_count):
    """Return a 0-5 list for star rendering loops."""
    return range(1, 6)
