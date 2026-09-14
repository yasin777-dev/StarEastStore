"""Expose the cart count for the navbar badge on every page."""
from .services import get_cart


def cart_summary(request):
    try:
        cart = get_cart(request)
        return {'cart_item_count': cart.count()}
    except Exception:
        return {'cart_item_count': 0}
