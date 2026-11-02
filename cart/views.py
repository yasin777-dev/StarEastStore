"""Cart views: add/update/remove/clear + cart page."""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


from products.models import Product

from .services import CartError, get_cart


def cart_detail(request):
    cart = get_cart(request)
    lines = cart.lines()
    subtotal = cart.subtotal()
    return render(request, 'cart/detail.html', {
        'lines': lines,
        'subtotal': subtotal,
        'count': cart.count(),
    })


def _positive_int(value) -> int | None:
    """Parse a posted id leniently.

    Returns None for blank/missing/garbage values so a malformed form post
    becomes a friendly message instead of a 500 from the ORM (``filter(pk='abc')``
    raises ValueError).
    """
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resolve_product(request):
    """Validate the posted product/variant ids. Returns (product, variant)."""
    product_id = _positive_int(request.POST.get('product_id'))
    variant_id = _positive_int(request.POST.get('variant_id'))
    if product_id is None:
        raise CartError('No product specified.')
    product = Product.objects.listed().filter(pk=product_id).first()
    if product is None:
        raise CartError('That product is no longer available.')
    variant = None
    if variant_id is not None:
        variant = product.variants.filter(pk=variant_id, is_active=True).first()
        if variant is None:
            raise CartError('That variant is no longer available.')
    return product, variant


def _parse_quantity(request) -> int:
    try:
        return int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        return 1


@require_POST
def cart_add(request):
    cart = get_cart(request)
    try:
        product, variant = _resolve_product(request)
        quantity = _parse_quantity(request)
        cart.add(product, variant, quantity)
        stored = next(
            (line.quantity for line in cart.lines()
             if line.product_id == product.pk
             and (line.variant_id or None) == (variant.pk if variant else None)),
            None,
        )
        if stored is not None and stored < max(1, quantity):
            messages.warning(
                request,
                f'Only {stored} unit(s) of "{product.name}" available — '
                'your quantity has been adjusted.',
            )
        else:
            messages.success(
                request,
                f'Added "{product.name}"'
                + (f' ({variant.display_name})' if variant else '')
                + f' × {stored or 1} to your cart.',
            )
    except CartError as exc:
        messages.error(request, str(exc))
    next_url = request.POST.get('next')
    if next_url == 'checkout':
        return redirect('orders:checkout')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect('cart:detail')


@require_POST
def cart_update(request):
    cart = get_cart(request)
    product_id = _positive_int(request.POST.get('product_id'))
    if product_id is None:
        messages.error(request, 'Invalid product.')
        return redirect('cart:detail')
    variant_id = _positive_int(request.POST.get('variant_id'))
    try:
        cart.update(product_id, variant_id, _parse_quantity(request))
    except CartError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Cart updated.')
    return redirect('cart:detail')


@require_POST
def cart_remove(request):
    cart = get_cart(request)
    product_id = _positive_int(request.POST.get('product_id'))
    if product_id is None:
        messages.error(request, 'Invalid product.')
        return redirect('cart:detail')
    variant_id = _positive_int(request.POST.get('variant_id'))
    try:
        cart.remove(product_id, variant_id)
        messages.success(request, 'Item removed from your cart.')
    except CartError as exc:
        messages.error(request, str(exc))
    return redirect('cart:detail')


@require_POST
def cart_clear(request):
    cart = get_cart(request)
    cart.clear()
    messages.success(request, 'Your cart has been emptied.')
    return redirect('cart:detail')
