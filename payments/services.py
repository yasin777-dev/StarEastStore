"""
Payment orchestration: initiation, idempotent completion, COD confirmation.

This module is the single place where an order transitions to "paid" - the
browser can never mark a payment as successful by itself.
"""
from __future__ import annotations


from django.db import transaction
from django.http import HttpResponse


from .gateways import GatewayError, available_gateways, get_gateway
from .models import PaymentTransaction, TransactionStatus


class PaymentError(Exception):
    pass


def available_payment_methods() -> list[tuple[str, str]]:
    """Choices for the checkout form: [(code, label), ...]."""
    return [
        ('cod', 'Cash on delivery'),
        *[(gateway.code, gateway.label) for gateway in available_gateways()],
    ]


def create_transaction(order, gateway_code: str) -> PaymentTransaction:
    return PaymentTransaction.objects.create(
        order=order,
        amount=order.total,
        gateway=gateway_code,
        status=TransactionStatus.PENDING,
    )


def initiate_payment(request, order) -> HttpResponse | None:
    """
    Kick off payment for a freshly placed order. Returns an HttpResponse to
    follow (redirect or template response), or None for cash on delivery.
    """
    from django.shortcuts import redirect, render

    if order.payment_method == 'cod':
        confirm_cash_on_delivery(order)
        return redirect(f'{order.get_absolute_url()}?placed=1')

    gateway = get_gateway(order.payment_method, request=request)
    txn = create_transaction(order, gateway.code)
    instructions = gateway.initiate(txn)
    if 'redirect_url' in instructions:
        return redirect(instructions['redirect_url'])
    if 'template' in instructions:
        return render(request, instructions['template'], instructions['context'])
    raise GatewayError(f'Gateway {gateway.code} returned no payment instructions.')


def retry_payment(request, order) -> HttpResponse:
    """Re-attempt payment for a pending order (customer clicked retry)."""
    from django.shortcuts import redirect

    if order.payment_method == 'cod':
        return redirect(order.get_absolute_url())
    if order.payment_status != 'pending':
        raise PaymentError('This order is no longer awaiting payment.')
    # Mark stale transactions cancelled, then start fresh.
    order.transactions.filter(status__in=['initiated', 'pending']).update(
        status=TransactionStatus.CANCELLED,
    )
    return initiate_payment(request, order)


@transaction.atomic
def verify_and_complete(reference: str, gateway_code: str, data: dict) -> PaymentTransaction:
    """
    Verify a payment server-side and complete the order. Idempotent: repeated
    calls (browser return + webhook) are safe and will not double-charge
    stock or coupons.
    """
    from orders.services import reduce_order_stock, record_status_change
    from orders.models import OrderStatus

    try:
        txn = (
            PaymentTransaction.objects.select_for_update()
            .select_related('order')
            .get(reference=reference, gateway=gateway_code)
        )
    except PaymentTransaction.DoesNotExist:
        raise PaymentError('Payment reference not found.')

    if txn.status == TransactionStatus.SUCCEEDED:
        return txn  # already completed - nothing to do
    if txn.status in {TransactionStatus.REFUNDED}:
        raise PaymentError('This payment has been refunded.')

    order = txn.order
    gateway = get_gateway(gateway_code)
    verified, failure_reason = gateway.verify(txn, data)

    if not verified:
        if failure_reason == 'cancelled':
            txn.status = TransactionStatus.CANCELLED
            txn.save(update_fields=['status', 'updated_at'])
            return txn
        txn.status = TransactionStatus.FAILED
        txn.failure_reason = (failure_reason or 'Verification failed')[:255]
        txn.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return txn

    # Verified by the gateway: capture money state, inventory and coupon.
    txn.status = TransactionStatus.SUCCEEDED
    txn.save(update_fields=['status', 'updated_at'])

    # Inventory: if stock evaporated between checkout and payment, keep the
    # money captured but hold the order for manual restock/refund - never
    # oversell and never crash the payment flow.
    from cart.services import CartError

    try:
        reduce_order_stock(order)
        stock_ok = True
    except CartError as exc:
        from orders.models import OrderStatusUpdate

        OrderStatusUpdate.objects.create(
            order=order, to_status=order.status,
            note=f'Stock unavailable at payment time: {exc}',
        )
        stock_ok = False

    order.payment_status = 'paid'
    if stock_ok and order.status in {OrderStatus.PENDING}:
        old_status = order.status
        order.status = OrderStatus.CONFIRMED
        order.save(update_fields=['payment_status', 'status', 'updated_at'])
        record_status_change(order, old_status, OrderStatus.CONFIRMED,
                             note='Payment verified - order confirmed')
    else:
        order.save(update_fields=['payment_status', 'updated_at'])

    if stock_ok and order.coupon_id:
        order.coupon.mark_used()

    _send_success_emails(order)
    return txn


def _send_success_emails(order) -> None:
    from orders.emails import (
        send_order_confirmation_email,
        send_payment_confirmation_email,
    )

    send_order_confirmation_email(order)
    send_payment_confirmation_email(order)


def mark_payment_failed(reference: str, gateway_code: str, reason: str) -> PaymentTransaction | None:
    """Record a failed attempt without touching the order's paid status."""
    txn = PaymentTransaction.objects.filter(
        reference=reference, gateway=gateway_code,
    ).first()
    if txn is None or txn.status == TransactionStatus.SUCCEEDED:
        return txn
    txn.status = TransactionStatus.FAILED
    txn.failure_reason = (reason or 'Payment failed')[:255]
    txn.save(update_fields=['status', 'failure_reason', 'updated_at'])
    return txn


def cancel_payment(reference: str, gateway_code: str) -> PaymentTransaction | None:
    txn = PaymentTransaction.objects.filter(
        reference=reference, gateway=gateway_code,
    ).first()
    if txn is None or txn.status == TransactionStatus.SUCCEEDED:
        return txn
    txn.status = TransactionStatus.CANCELLED
    txn.save(update_fields=['status', 'updated_at'])
    return txn


@transaction.atomic
def confirm_cash_on_delivery(order) -> None:
    """Confirm a COD order: reserve stock now, collect cash at delivery."""
    from orders.services import reduce_order_stock, record_status_change
    from orders.models import OrderStatus

    if order.payment_status == 'cod_pending':
        return  # idempotent
    reduce_order_stock(order)
    old_status = order.status
    order.payment_status = 'cod_pending'
    order.status = OrderStatus.CONFIRMED
    order.save(update_fields=['payment_status', 'status', 'updated_at'])
    record_status_change(order, old_status, OrderStatus.CONFIRMED,
                         note='Cash on delivery - order confirmed')
    _send_success_emails(order)
