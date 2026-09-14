"""Order + payment notification emails (section 19)."""
from __future__ import annotations

from core.emails import send_templated_email


def _send_order_email(order, subject_tpl: str, body_tpl: str) -> bool:
    return send_templated_email(
        subject_tpl, body_tpl, {'order': order, 'shop_name': None}, order.email,
    )


def send_order_confirmation_email(order) -> bool:
    return _send_order_email(order, 'emails/order_confirmation_subject.txt', 'emails/order_confirmation.txt')


def send_payment_confirmation_email(order) -> bool:
    return _send_order_email(order, 'emails/payment_confirmation_subject.txt', 'emails/payment_confirmation.txt')


def send_order_shipped_email(order) -> bool:
    return _send_order_email(order, 'emails/order_shipped_subject.txt', 'emails/order_shipped.txt')


def send_order_delivered_email(order) -> bool:
    return _send_order_email(order, 'emails/order_delivered_subject.txt', 'emails/order_delivered.txt')


def send_order_cancelled_email(order) -> bool:
    return _send_order_email(order, 'emails/order_cancelled_subject.txt', 'emails/order_cancelled.txt')
