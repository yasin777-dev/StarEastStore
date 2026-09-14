"""
Order business logic: totals, checkout, status changes and cancellation.

Every monetary figure is computed here on the backend from database state;
nothing is ever trusted from the browser (section 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction


from .models import (
    Coupon, Order, OrderItem, OrderStatus, OrderStatusUpdate,
    PaymentStatus, ShippingMethod,
)


class CheckoutError(Exception):
    """Raised when an order cannot be placed."""


@dataclass
class OrderTotals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping_fee: Decimal
    total: Decimal
    coupon: Coupon | None = None
    shipping_method: ShippingMethod | None = None


def compute_totals(
    subtotal: Decimal,
    coupon: Coupon | None = None,
    shipping_method: ShippingMethod | None = None,
) -> OrderTotals:
    """Single source of truth for order maths (backend only)."""
    discount = Decimal('0.00')
    if coupon is not None:
        discount = coupon.discount_for(subtotal)

    discounted_subtotal = subtotal - discount

    shipping_fee = Decimal('0.00')
    if shipping_method is not None:
        shipping_fee = shipping_method.price
        threshold = getattr(settings, 'FREE_SHIPPING_THRESHOLD', None)
        if threshold is not None and discounted_subtotal >= threshold:
            shipping_fee = Decimal('0.00')

    tax_rate = getattr(settings, 'TAX_RATE', Decimal('0.00'))
    tax = (discounted_subtotal * tax_rate).quantize(Decimal('0.01'))

    total = (discounted_subtotal + tax + shipping_fee).quantize(Decimal('0.01'))
    return OrderTotals(
        subtotal=subtotal.quantize(Decimal('0.01')),
        discount=discount,
        tax=tax,
        shipping_fee=shipping_fee,
        total=total,
        coupon=coupon,
        shipping_method=shipping_method,
    )


def resolve_coupon(code: str | None) -> tuple[Coupon | None, str | None]:
    """Return (coupon, error). Coupon is None when no code supplied/invalid."""
    code = (code or '').strip().upper()
    if not code:
        return None, None
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None:
        return None, f'Coupon "{code}" was not found.'
    error = coupon.validation_error()
    if error:
        return None, error
    return coupon, None


@transaction.atomic
def place_order(*, user, cart, address, shipping_method_id, coupon_code='',
                payment_method: str, customer_note: str = '') -> Order:
    """
    Validate everything again server-side and create a pending Order.

    The caller is responsible for initiating payment afterwards. Stock is
    reduced once payment succeeds (or immediately for cash on delivery).
    """
    lines = cart.lines()
    if not lines:
        raise CheckoutError('Your cart is empty.')

    # Re-validate stock against live inventory before accepting the order.
    for line in lines:
        available = line.available_stock
        if available < line.quantity:
            raise CheckoutError(
                f'Insufficient stock for "{line.product.name}"'
                + (f' ({line.variant.display_name})' if line.variant else '')
                + f'. Only {available} left. Please update your cart.'
            )

    coupon, coupon_error = resolve_coupon(coupon_code)
    if coupon_error:
        raise CheckoutError(coupon_error)

    shipping_method = None
    if shipping_method_id:
        shipping_method = ShippingMethod.objects.filter(
            pk=shipping_method_id, is_active=True,
        ).first()
        if shipping_method is None:
            raise CheckoutError('Please choose a valid shipping method.')

    totals = compute_totals(cart.subtotal(), coupon, shipping_method)

    order = Order(
        user=user,
        email=user.email,
        shipping_full_name=address.full_name,
        shipping_phone=address.phone,
        shipping_address_line_1=address.address_line_1,
        shipping_address_line_2=address.address_line_2,
        shipping_city=address.city,
        shipping_state=address.state,
        shipping_postal_code=address.postal_code,
        shipping_country=address.country,
        subtotal=totals.subtotal,
        discount=totals.discount,
        tax=totals.tax,
        shipping_fee=totals.shipping_fee,
        total=totals.total,
        coupon=coupon,
        shipping_method=shipping_method,
        shipping_method_name=shipping_method.name if shipping_method else '',
        payment_method=payment_method,
        customer_note=customer_note[:500] if customer_note else '',
    )
    order.save()

    for line in lines:
        OrderItem.from_cart_line(order, line).save()

    OrderStatusUpdate.objects.create(
        order=order, from_status='', to_status=OrderStatus.PENDING,
        changed_by=user, note='Order placed.',
    )

    cart.clear()
    return order


@transaction.atomic
def reduce_order_stock(order: Order) -> None:
    """Deduct inventory once per order (idempotent, row-level locking)."""
    if order.stock_deducted:
        return
    from cart.services import reduce_stock_for_line

    for item in order.items.select_related('product', 'variant'):
        reduce_stock_for_line(item.product, item.variant, item.quantity)
    order.stock_deducted = True
    order.save(update_fields=['stock_deducted', 'updated_at'])


@transaction.atomic
def restore_order_stock(order: Order) -> None:
    """Return inventory once per order (idempotent)."""
    if not order.stock_deducted:
        return
    from cart.services import restore_stock_for_line

    for item in order.items.select_related('product', 'variant'):
        restore_stock_for_line(item.product, item.variant, item.quantity)
    order.stock_deducted = False
    order.save(update_fields=['stock_deducted', 'updated_at'])


def record_status_change(order: Order, old_status: str, new_status: str, *,
                         changed_by=None, note: str = '') -> None:
    """Persist an OrderStatusUpdate row and send the matching email."""
    from .emails import (
        send_order_cancelled_email,
        send_order_delivered_email,
        send_order_shipped_email,
    )

    OrderStatusUpdate.objects.create(
        order=order, from_status=old_status or '', to_status=new_status,
        changed_by=changed_by, note=note[:255] if note else '',
    )
    if new_status == OrderStatus.SHIPPED:
        send_order_shipped_email(order)
    elif new_status == OrderStatus.DELIVERED:
        send_order_delivered_email(order)
    elif new_status == OrderStatus.CANCELLED:
        send_order_cancelled_email(order)


def set_order_status(order: Order, new_status: str, *, changed_by=None, note: str = '',
                     notify_customer: bool = True) -> None:
    """Change status, record the audit trail and notify the customer."""
    old_status = order.status
    if old_status == new_status:
        return
    order.status = new_status
    order.save(update_fields=['status', 'updated_at'])
    if notify_customer:
        record_status_change(order, old_status, new_status, changed_by=changed_by,
                             note=note)
    else:
        OrderStatusUpdate.objects.create(
            order=order, from_status=old_status or '', to_status=new_status,
            changed_by=changed_by, note=note[:255] if note else '',
        )


@transaction.atomic
def cancel_order(order: Order, *, changed_by=None, notify: bool = True) -> None:
    """
    Customer/admin cancellation. Restores stock and marks any paid
    transaction as refunded. Raises CheckoutError if not cancellable.
    """
    if not order.can_be_cancelled_by_customer:
        raise CheckoutError('This order can no longer be cancelled.')

    restore_order_stock(order)

    # If money was already captured online, flip the transaction + order to
    # refunded so finance can settle it with the gateway.
    paid_transaction = order.transactions.filter(status='succeeded').first()
    if paid_transaction:
        paid_transaction.status = 'refunded'
        paid_transaction.save(update_fields=['status', 'updated_at'])
        order.payment_status = PaymentStatus.REFUNDED
        order.save(update_fields=['payment_status', 'updated_at'])

    set_order_status(
        order, OrderStatus.CANCELLED, changed_by=changed_by,
        note='Cancelled by ' + ('admin' if changed_by and changed_by.is_staff else 'customer'),
        notify_customer=False,
    )
    if notify:
        from .emails import send_order_cancelled_email

        send_order_cancelled_email(order)


def order_totals_for_display(order: Order) -> dict:
    return {
        'subtotal': order.subtotal,
        'discount': order.discount,
        'tax': order.tax,
        'shipping_fee': order.shipping_fee,
        'total': order.total,
    }
