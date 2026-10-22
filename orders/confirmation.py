"""One-time order confirmation, issued by the server after successful checkout."""
from django.shortcuts import redirect

from .models import OrderStatus, PaymentStatus

SESSION_KEY = 'checkout_success_order'


def order_confirmation_redirect(request, order):
    """Remember the saved order for the next detail page, not an arbitrary URL flag."""
    request.session[SESSION_KEY] = order.order_number
    return redirect(f'{order.get_absolute_url()}?placed=1')


def consume_order_confirmation(request, order):
    """Show success once, only to the owner of a successfully confirmed order."""
    if request.session.get(SESSION_KEY) != order.order_number:
        return False
    request.session.pop(SESSION_KEY)
    return (
        order.status in {
            OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
            OrderStatus.SHIPPED, OrderStatus.DELIVERED,
        }
        and order.payment_status in {PaymentStatus.PAID, PaymentStatus.COD_PENDING}
    )
