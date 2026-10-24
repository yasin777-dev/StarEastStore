"""Checkout, order list/detail and cancellation views."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.services import CartError, get_cart

from .confirmation import consume_order_confirmation
from .forms import CheckoutForm
from .models import Order, PaymentStatus, ShippingMethod
from .services import (
    CheckoutError,
    cancel_order,
    compute_totals,
    format_money,
    place_order,
    resolve_coupon,
)


def _cart_lines(request):
    cart = get_cart(request)
    lines = cart.lines()
    # Drop phantom lines defensively; also refresh any stale quantity.
    return cart, lines


COUPON_ACTIONS = {'apply_coupon', 'remove_coupon'}


def _selected_shipping_method(request):
    """Shipping method used for the live totals preview."""
    if request.method == 'POST':
        raw = request.POST.get('shipping_method')
        if raw:
            method = ShippingMethod.objects.filter(pk=raw, is_active=True).first()
            if method is not None:
                return method
    return ShippingMethod.objects.filter(is_active=True).first()


@login_required
def checkout(request):
    cart, lines = _cart_lines(request)
    if not lines:
        messages.info(request, 'Your cart is empty. Add some products first.')
        return redirect('products:list')

    from payments.gateways import GatewayError
    from payments.services import (
        PaymentError, available_payment_methods, confirm_cash_on_delivery, initiate_payment,
    )

    methods = available_payment_methods()
    subtotal = cart.subtotal()
    action = request.POST.get('action', 'place_order') if request.method == 'POST' else ''

    # Applying or removing a coupon must never require the rest of the
    # checkout form (address, shipping, payment) to be filled in first.
    if action in COUPON_ACTIONS:
        data = request.POST.copy()
        requested = (data.get('coupon_code') or '').strip()
        if action == 'remove_coupon':
            data['coupon_code'] = ''
            messages.info(request, 'Coupon removed. Your total has been updated.')
        elif not requested:
            messages.info(request, 'Type a coupon code first, then press Apply.')
        else:
            coupon, error = resolve_coupon(requested, subtotal)
            if error:
                messages.error(request, error)
            else:
                data['coupon_code'] = coupon.code
                messages.success(
                    request,
                    f'Coupon "{coupon.code}" applied. You save '
                    f'{format_money(coupon.discount_for(subtotal))}.',
                )
        form = CheckoutForm(data, user=request.user, available_payment_methods=methods)
        return render(request, 'orders/checkout.html', _checkout_context(
            request, form, lines, subtotal, methods,
            coupon_code=data.get('coupon_code', ''),
            shipping_method=_selected_shipping_method(request),
            show_form_errors=False,
        ))

    if request.method == 'POST':
        form = CheckoutForm(
            request.POST, user=request.user, available_payment_methods=methods,
        )
        if form.is_valid():
            try:
                # COD confirmation and the order/items/cart writes must succeed
                # together. A stock race must not leave a cleared cart or a
                # partially placed order behind.
                with transaction.atomic():
                    order = place_order(
                        user=request.user,
                        cart=cart,
                        address=form.cleaned_data['address_id'],
                        shipping_method_id=form.cleaned_data['shipping_method'].pk,
                        coupon_code=form.cleaned_data.get('coupon_code', ''),
                        payment_method=form.cleaned_data['payment_method'],
                        customer_note=form.cleaned_data.get('customer_note', ''),
                    )
                    if order.payment_method == 'cod':
                        confirm_cash_on_delivery(order)
            except (CheckoutError, CartError) as exc:
                form.add_error(None, str(exc))
            else:
                # The order is committed before contacting an external gateway.
                # A payment outage must not hide an already saved order.
                try:
                    response = initiate_payment(request, order)
                except (GatewayError, PaymentError):
                    messages.warning(
                        request,
                        'Your order is saved, but we could not start the payment. '
                        'Please retry payment from your order details.',
                    )
                else:
                    if response is not None:
                        return response
                return redirect('orders:detail', order.order_number)
    else:
        form = CheckoutForm(user=request.user, available_payment_methods=methods)
        default_address = (
            request.user.addresses.filter(is_default=True).first()
            or request.user.addresses.first()
        )
        if default_address:
            form.initial['address_id'] = default_address.pk
        first_method = ShippingMethod.objects.filter(is_active=True).first()
        if first_method:
            form.initial['shipping_method'] = first_method.pk
        if methods:
            form.initial['payment_method'] = methods[0][0]

    return render(request, 'orders/checkout.html', _checkout_context(
        request, form, lines, subtotal, methods,
        coupon_code=form.data.get('coupon_code', '') if form.is_bound else '',
        shipping_method=_selected_shipping_method(request),
    ))


def _checkout_context(request, form, lines, subtotal, methods, coupon_code='',
                      shipping_method=None, show_form_errors=True):
    # The coupon lives only in this page's form until the order is placed, so
    # the preview is recomputed from the posted code on every render.
    coupon, _error = resolve_coupon(coupon_code, subtotal)
    totals = compute_totals(subtotal, coupon, shipping_method)
    return {
        'form': form,
        'lines': lines,
        'subtotal': totals.subtotal,
        'discount': totals.discount,
        'shipping_fee': totals.shipping_fee,
        'tax': totals.tax,
        'grand_total': totals.total,
        'payment_methods': methods,
        'shipping_available': form.fields['shipping_method'].queryset.exists(),
        'shipping_method': totals.shipping_method,
        'addresses': request.user.addresses.all(),
        'coupon_code': coupon_code,
        'applied_coupon': coupon,
        'show_form_errors': show_form_errors,
    }


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items')
    paginator = Paginator(orders, 10)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'orders/order_list.html', {'page_obj': page})


@login_required
def order_detail(request, order_number: str):
    order = get_object_or_404(
        Order.objects.prefetch_related('items', 'status_updates', 'transactions'),
        order_number=order_number, user=request.user,
    )
    transaction_row = order.current_transaction()
    return render(request, 'orders/order_detail.html', {
        'order': order,
        'transaction_row': transaction_row,
        'just_placed': consume_order_confirmation(request, order),
    })


@login_required
@require_POST
def order_cancel(request, order_number: str):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    try:
        cancel_order(order, changed_by=request.user)
        messages.success(
            request,
            f'Order {order.order_number} has been cancelled.'
            + (' Any paid amount will be refunded.' if order.payment_status == PaymentStatus.REFUNDED else ''),
        )
    except CheckoutError as exc:
        messages.error(request, str(exc))
    return redirect('orders:detail', order.order_number)
