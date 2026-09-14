"""Context processors exposing shop-wide settings to every template."""
from django.conf import settings


def shop_settings(request):
    return {
        'SHOP_NAME': settings.SHOP_NAME,
        'SHOP_TAGLINE': settings.SHOP_TAGLINE,
        'CURRENCY': settings.CURRENCY,
        'FREE_SHIPPING_THRESHOLD': settings.FREE_SHIPPING_THRESHOLD,
        'TAX_RATE': settings.TAX_RATE,
    }
