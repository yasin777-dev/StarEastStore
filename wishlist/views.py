"""Wishlist views: toggle, list, move-to-cart, remove."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.services import CartError, get_cart
from products.models import Product

from .models import WishlistItem


@login_required
@require_POST
def toggle(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
        messages.success(request, f'"{product.name}" removed from your wishlist.')
    else:
        messages.success(request, f'"{product.name}" added to your wishlist.')
    return redirect(request.POST.get('next') or product.get_absolute_url())


@login_required
def wishlist_detail(request):
    items = (
        WishlistItem.objects.filter(user=request.user)
        .select_related('product', 'product__category', 'product__brand')
        .prefetch_related('product__images')
    )
    return render(request, 'wishlist/wishlist.html', {'items': items})


@login_required
@require_POST
def remove(request, pk: int):
    item = get_object_or_404(WishlistItem, pk=pk, user=request.user)
    item.delete()
    messages.success(request, 'Item removed from your wishlist.')
    return redirect('wishlist:detail')


@login_required
@require_POST
def move_to_cart(request, pk: int):
    """Move a wishlist entry into the cart (and drop it from the wishlist)."""
    item = get_object_or_404(
        WishlistItem.objects.select_related('product'), pk=pk, user=request.user,
    )
    product = item.product
    if not product.is_active:
        messages.error(request, 'That product is no longer available.')
        return redirect('wishlist:detail')
    cart = get_cart(request)
    try:
        cart.add(product, None, 1)
    except CartError as exc:
        messages.error(request, str(exc))
        return redirect('wishlist:detail')
    item.delete()
    messages.success(request, f'"{product.name}" moved to your cart.')
    return redirect('cart:detail')
