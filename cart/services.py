"""
Cart services (section 5).

Two interchangeable backends implement the same interface:

* ``SessionCart``  - guest users, stored in the Django session.
* ``DatabaseCart`` - authenticated users, stored in the database.

All price/total calculations happen here on the backend; the frontend only
displays what the backend returns and never sends prices back.
"""
from __future__ import annotations

from dataclasses import dataclass

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F

from .models import Cart, CartItem

MAX_LINE_QUANTITY = settings.MAX_LINE_QUANTITY


class CartError(Exception):
    """Raised for invalid cart operations (stock limits, bad input...)."""


@dataclass
class CartLine:
    product_id: int
    variant_id: int | None
    product: object
    variant: object | None
    quantity: int

    @property
    def unit_price(self) -> Decimal:
        if self.variant is not None:
            return self.variant.effective_price
        return self.product.effective_price

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def available_stock(self) -> int:
        return self.product.available_stock_for(self.variant)

    @property
    def line_key(self) -> str:
        return f'{self.product_id}:{self.variant_id or 0}'


class BaseCart:
    """Common read-side behaviour shared by both backends."""

    def lines(self) -> list[CartLine]:
        raise NotImplementedError

    def count(self) -> int:
        return sum(line.quantity for line in self.lines())

    def subtotal(self) -> Decimal:
        return sum((line.line_total for line in self.lines()), Decimal('0.00'))

    def is_empty(self) -> bool:
        return not self.lines()

    def to_dict(self) -> dict:
        return {
            'count': self.count(),
            'subtotal': str(self.subtotal()),
            'lines': [
                {
                    'product_id': line.product_id,
                    'variant_id': line.variant_id,
                    'product_name': line.product.name,
                    'variant_name': line.variant.display_name if line.variant else '',
                    'quantity': line.quantity,
                    'unit_price': str(line.unit_price),
                    'line_total': str(line.line_total),
                    'product_url': line.product.get_absolute_url(),
                    'in_stock': line.available_stock >= line.quantity,
                }
                for line in self.lines()
            ],
        }


def _load_line_objects(raw_items: list[dict]) -> list[CartLine]:
    """Resolve (product_id, variant_id, quantity) tuples into CartLines.

    Silently drops entries whose product/variant has been deleted or
    deactivated since being added.
    """
    from products.models import Product

    lines: list[CartLine] = []
    for raw in raw_items:
        try:
            product_id = int(raw['product_id'])
            variant_id = int(raw['variant_id']) if raw.get('variant_id') else None
            quantity = int(raw['quantity'])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            product = Product.objects.listed().select_related('category', 'brand').get(
                pk=product_id,
            )
            variant = None
            if variant_id:
                variant = product.variants.filter(pk=variant_id, is_active=True).first()
        except Product.DoesNotExist:
            continue
        if quantity <= 0:
            continue
        lines.append(CartLine(product.id, variant.id if variant else None,
                              product, variant, quantity))
    return lines


class SessionCart(BaseCart):
    """Guest cart persisted in request.session (no login required)."""

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.session.setdefault(settings.CART_SESSION_KEY, {})

    def _raw(self) -> dict:
        return self.session.get(settings.CART_SESSION_KEY, {})

    def _save(self, raw: dict) -> None:
        self.session[settings.CART_SESSION_KEY] = raw
        self.session.modified = True

    def lines(self) -> list[CartLine]:
        raw_items = []
        for key, qty in self._raw().items():
            pid, _, vid = str(key).partition(':')
            raw_items.append({
                'product_id': pid, 'variant_id': vid or None, 'quantity': qty,
            })
        return _load_line_objects(raw_items)

    def _key(self, product_id: int, variant_id: int | None) -> str:
        return f'{product_id}:{variant_id or 0}'

    def add(self, product, variant=None, quantity: int = 1, replace: bool = False):
        key = self._key(product.id, variant.id if variant else None)
        raw = self._raw()
        current = int(raw.get(key, 0))
        new_qty = quantity if replace else current + quantity
        new_qty = _validate_quantity(product, variant, new_qty)
        raw[key] = new_qty
        self._save(raw)

    def update(self, product_id: int, variant_id: int | None, quantity: int):
        key = self._key(product_id, variant_id)
        raw = self._raw()
        if key not in raw:
            raise CartError('Item not found in cart.')
        if quantity <= 0:
            del raw[key]
            self._save(raw)
            return
        from products.models import Product

        product = Product.objects.get(pk=product_id)
        variant = product.variants.filter(pk=variant_id).first() if variant_id else None
        raw[key] = _validate_quantity(product, variant, quantity)
        self._save(raw)

    def remove(self, product_id: int, variant_id: int | None = None):
        key = self._key(product_id, variant_id)
        raw = self._raw()
        if key not in raw:
            raise CartError('Item not found in cart.')
        del raw[key]
        self._save(raw)

    def clear(self) -> None:
        self._save({})

    def as_session_dict(self) -> dict:
        return dict(self._raw())


class DatabaseCart(BaseCart):
    """Persisted cart for logged-in customers."""

    def __init__(self, user):
        self.user = user
        self.cart, _ = Cart.objects.get_or_create(user=user)

    def lines(self) -> list[CartLine]:
        items = (
            CartItem.objects.filter(cart=self.cart)
            .select_related('product', 'variant', 'product__category', 'product__brand')
        )
        lines = []
        for item in items:
            # Drop items whose product has since been deactivated.
            if not item.product.is_active:
                item.delete()
                continue
            if item.variant is not None and not item.variant.is_active:
                item.delete()
                continue
            lines.append(CartLine(
                item.product_id, item.variant_id, item.product, item.variant,
                item.quantity,
            ))
        return lines

    def add(self, product, variant=None, quantity: int = 1, replace: bool = False):
        item, _created = CartItem.objects.get_or_create(
            cart=self.cart, product=product, variant=variant,
            defaults={'quantity': 0},
        )
        new_qty = quantity if replace else item.quantity + quantity
        item.quantity = _validate_quantity(product, variant, new_qty)
        item.save()

    def update(self, product_id: int, variant_id: int | None, quantity: int):
        try:
            item = CartItem.objects.get(cart=self.cart, product_id=product_id,
                                        variant_id=variant_id)
        except CartItem.DoesNotExist:
            raise CartError('Item not found in cart.')
        if quantity <= 0:
            item.delete()
            return
        variant = item.variant
        item.quantity = _validate_quantity(item.product, variant, quantity)
        item.save()

    def remove(self, product_id: int, variant_id: int | None = None):
        deleted, _ = CartItem.objects.filter(
            cart=self.cart, product_id=product_id, variant_id=variant_id,
        ).delete()
        if not deleted:
            raise CartError('Item not found in cart.')

    def clear(self) -> None:
        self.cart.items.all().delete()


def _validate_quantity(product, variant, quantity: int) -> int:
    """
    Clamp the requested quantity to available stock and the global cap.

    Overselling is impossible: requests beyond available stock are clamped
    down and the caller surfaces a notice. Zero stock is an outright error.
    """
    quantity = max(1, min(int(quantity), MAX_LINE_QUANTITY))
    available = product.available_stock_for(variant)
    if available <= 0:
        raise CartError(f'Sorry, "{product.name}" is out of stock.')
    return min(quantity, available)


def get_cart(request):
    """Return the cart backend matching the request's auth state."""
    if request.user.is_authenticated:
        return DatabaseCart(request.user)
    return SessionCart(request)


@transaction.atomic
def merge_session_cart_into_user_cart(request, user) -> None:
    """On login: move guest cart lines into the persisted cart."""
    if not hasattr(request, 'session'):
        return
    guest = SessionCart(request)
    raw_items = []
    for key, qty in guest.as_session_dict().items():
        pid, _, vid = str(key).partition(':')
        raw_items.append({'product_id': pid, 'variant_id': vid or None,
                          'quantity': qty})
    if not raw_items:
        return
    user_cart = DatabaseCart(user)
    for line in _load_line_objects(raw_items):
        try:
            user_cart.add(line.product, line.variant, line.quantity)
        except CartError:
            # Out of stock / invalid items are dropped silently on merge.
            continue
    guest.clear()


@transaction.atomic
def reduce_stock_for_line(product, variant, quantity: int) -> None:
    """
    Atomically decrement stock with row-level locking (section 14).

    ``select_for_update`` is a no-op on SQLite but enforces serialised
    updates on PostgreSQL, preventing overselling under concurrency.
    """
    from products.models import Product, ProductVariant

    if variant is not None:
        locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        if locked.stock_quantity < quantity:
            raise CartError(f'Insufficient stock for {product.name} ({locked.display_name}).')
        ProductVariant.objects.filter(pk=locked.pk).update(
            stock_quantity=F('stock_quantity') - quantity,
        )
        # Roll variant sales up into the parent product's popularity counter.
        Product.objects.filter(pk=product.pk).update(
            total_sales=F('total_sales') + quantity,
        )
    else:
        locked = Product.objects.select_for_update().get(pk=product.pk)
        if locked.stock_quantity < quantity:
            raise CartError(f'Insufficient stock for {locked.name}.')
        Product.objects.filter(pk=locked.pk).update(
            stock_quantity=F('stock_quantity') - quantity,
            total_sales=F('total_sales') + quantity,
        )


@transaction.atomic
def restore_stock_for_line(product, variant, quantity: int) -> None:
    """Return reserved stock to inventory (cancellation/refund)."""
    from django.db.models.functions import Greatest

    from products.models import Product, ProductVariant

    if variant is not None:
        ProductVariant.objects.filter(pk=variant.pk).update(
            stock_quantity=F('stock_quantity') + quantity,
        )
    else:
        Product.objects.filter(pk=product.pk).update(
            stock_quantity=F('stock_quantity') + quantity,
        )
    Product.objects.filter(pk=product.pk).update(
        total_sales=Greatest(F('total_sales') - quantity, 0),
    )
