"""Payment flow views: simulated gateway page, verification, webhooks."""
from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from orders.models import Order

from .gateways import GatewayError, get_gateway
from .models import PaymentTransaction, TransactionStatus
from .services import (
    PaymentError,
    cancel_payment,
    retry_payment,
    verify_and_complete,
)

logger = logging.getLogger(__name__)


def _get_pending_txn(request, reference: str) -> PaymentTransaction:
    """Load the transaction, ensuring it belongs to the current customer."""
    txn = get_object_or_404(
        PaymentTransaction.objects.select_related('order'),
        reference=reference,
    )
    if request.user.is_authenticated and txn.order.user_id != request.user.id:
        raise PermissionError('You do not have access to this payment.')
    return txn


def simulate_payment(request, reference: str):
    """Demo gateway page: shows the amount and lets the user pay/fail/cancel."""
    try:
        txn = _get_pending_txn(request, reference)
    except PermissionError:
        return redirect('orders:list')
    if txn.gateway != 'simulated':
        return redirect('orders:detail', txn.order.order_number)
    if txn.status == TransactionStatus.SUCCEEDED:
        return redirect(f'{txn.order.get_absolute_url()}?placed=1')
    return render(request, 'payments/simulate.html', {
        'txn': txn,
        'order': txn.order,
    })


@require_POST
def simulate_process(request, reference: str):
    try:
        txn = _get_pending_txn(request, reference)
    except PermissionError:
        return redirect('orders:list')
    if txn.gateway != 'simulated' or txn.status == TransactionStatus.SUCCEEDED:
        return redirect('orders:detail', txn.order.order_number)

    outcome = request.POST.get('outcome', 'failure')
    order = txn.order
    try:
        result = verify_and_complete(txn.reference, 'simulated', {'outcome': outcome})
    except PaymentError as exc:
        messages.error(request, str(exc))
        return redirect('orders:detail', order.order_number)

    if result.status == TransactionStatus.SUCCEEDED:
        messages.success(request, 'Payment successful! Thank you for your purchase.')
        return redirect(f'{order.get_absolute_url()}?placed=1')
    if result.status == TransactionStatus.CANCELLED:
        messages.info(request, 'Payment cancelled. You can retry whenever you like.')
        return redirect('orders:detail', order.order_number)
    messages.error(
        request,
        'Payment failed: '
        + (result.failure_reason or 'the demo gateway declined the payment.')
        + ' You can try again.',
    )
    return redirect('orders:detail', order.order_number)


def verify_payment(request, reference: str):
    """
    Browser-return endpoint (e.g. Stripe success_url). Verification happens
    against the gateway API, never against what the browser claims.
    """
    try:
        txn = _get_pending_txn(request, reference)
    except PermissionError:
        return redirect('orders:list')
    order = txn.order
    data = {
        'session_id': request.GET.get('session_id', ''),
        **{key: request.POST.get(key, '') for key in
           ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature')},
    }
    try:
        result = verify_and_complete(reference, txn.gateway, data)
    except (PaymentError, GatewayError) as exc:
        logger.warning('Payment verification error for %s: %s', reference, exc)
        messages.error(request, 'We could not verify your payment. Please contact support.')
        return redirect('orders:detail', order.order_number)

    if result.status == TransactionStatus.SUCCEEDED:
        messages.success(request, 'Payment verified - thank you!')
        return redirect(f'{order.get_absolute_url()}?placed=1')
    messages.error(request, 'Your payment has not been completed yet.')
    return redirect('orders:detail', order.order_number)


def cancel_payment_view(request, reference: str):
    try:
        txn = _get_pending_txn(request, reference)
    except PermissionError:
        return redirect('orders:list')
    cancel_payment(reference, txn.gateway)
    messages.info(request, 'Payment cancelled. Your order is saved and awaiting payment.')
    return redirect('orders:detail', txn.order.order_number)


@require_POST
def retry_payment_view(request, order_number: str):
    order = get_object_or_404(Order, order_number=order_number)
    if request.user.is_authenticated and order.user_id != request.user.id:
        messages.error(request, 'You do not have access to this order.')
        return redirect('orders:list')
    try:
        return retry_payment(request, order)
    except (PaymentError, GatewayError) as exc:
        messages.error(request, str(exc))
        return redirect('orders:detail', order.order_number)


@csrf_exempt
@require_POST
def webhook(request, gateway_code: str):
    """
    Gateway webhooks are the trusted server-to-server channel. Processing is
    idempotent (verify_and_complete short-circuits completed payments).
    """
    try:
        gateway = get_gateway(gateway_code)
    except GatewayError:
        return HttpResponseBadRequest('Unknown gateway')

    try:
        reference, ok = gateway.handle_webhook(request.body, dict(request.headers))
    except NotImplementedError:
        return HttpResponseBadRequest('Gateway does not support webhooks')
    if not reference or not ok:
        logger.warning('Rejected %s webhook (ok=%s, ref=%s)', gateway_code, ok, reference)
        return HttpResponseBadRequest('Invalid webhook')

    try:
        txn = verify_and_complete(reference, gateway_code, {'source': 'webhook'})
    except PaymentError as exc:
        logger.warning('Webhook completion failed for %s: %s', reference, exc)
        return JsonResponse({'received': True, 'processed': False})
    return JsonResponse({'received': True, 'status': txn.status})
