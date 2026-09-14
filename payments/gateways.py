"""
Payment gateway abstraction (section 10).

``BaseGateway`` defines the contract every gateway must fulfil:

* ``is_available``       - configured & SDK importable?
* ``initiate``           - create a payment with the gateway, return instructions
* ``verify``             - server-side verification (never trust the browser)
* ``handle_webhook``     - parse/verify a webhook payload, return (reference, ok)

Available implementations:

* ``SimulatedGateway`` - built-in demo gateway (development only)
* ``StripeGateway``    - Stripe Checkout (requires the ``stripe`` package + keys)
* ``RazorpayGateway``  - Razorpay Orders (requires the ``razorpay`` package + keys)
"""
from __future__ import annotations

import hmac
import hashlib
from abc import ABC, abstractmethod

from django.conf import settings
from django.urls import reverse

PAYMENT_SETTINGS = settings.PAYMENT_SETTINGS


class GatewayError(Exception):
    pass


class BaseGateway(ABC):
    code: str = ''
    label: str = ''
    description: str = ''

    def __init__(self, request=None):
        self.request = request

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool: ...

    @abstractmethod
    def initiate(self, transaction) -> dict:
        """Create the payment. Returns instructions for the caller:
        {'redirect_url': ...} or {'template': ..., 'context': {...}}."""

    @abstractmethod
    def verify(self, transaction, data: dict) -> tuple[bool, str | None]:
        """Server-side verification. Returns (verified, failure_reason)."""

    def handle_webhook(self, payload: bytes, headers: dict) -> tuple[str | None, bool]:
        """Process a webhook. Returns (transaction_reference, success)."""
        raise NotImplementedError


def _absolute_url(request, path: str) -> str:
    if request is not None:
        return request.build_absolute_uri(path)
    return path


class SimulatedGateway(BaseGateway):
    """Development/demo gateway. Verification is deterministic server-side."""

    code = 'simulated'
    label = 'Demo gateway (card simulation)'
    description = 'Simulated card payment for development and demos.'

    @classmethod
    def is_available(cls) -> bool:
        return bool(settings.SIMULATED_GATEWAY_ENABLED)

    def initiate(self, transaction) -> dict:
        transaction.status = 'pending'
        transaction.transaction_id = f'SIM-{transaction.reference[:12].upper()}'
        transaction.gateway_response = {'gateway': 'simulated', 'txn_id': transaction.transaction_id}
        transaction.save(update_fields=['status', 'transaction_id', 'gateway_response', 'updated_at'])
        url = reverse('payments:simulate', kwargs={'reference': transaction.reference})
        return {'redirect_url': _absolute_url(self.request, url)}

    def verify(self, transaction, data: dict) -> tuple[bool, str | None]:
        # Server-side "gateway decision": only an explicit success flag is
        # honoured, mirroring how a real gateway would report the outcome.
        outcome = data.get('outcome')
        transaction.gateway_response = {
            **transaction.gateway_response,
            'verify_outcome': outcome,
        }
        transaction.save(update_fields=['gateway_response', 'updated_at'])
        if outcome == 'success':
            return True, None
        if outcome == 'cancel':
            return False, 'cancelled'
        return False, data.get('reason') or 'Payment was declined by the demo gateway.'


class StripeGateway(BaseGateway):
    """Stripe Checkout Session flow."""

    code = 'stripe'
    label = 'Credit / debit card (Stripe)'
    description = 'Secure card payment powered by Stripe.'

    @classmethod
    def is_available(cls) -> bool:
        try:
            import stripe  # noqa: F401
        except ImportError:
            return False
        return bool(PAYMENT_SETTINGS.get('STRIPE_SECRET_KEY'))

    def _client(self):
        import stripe

        stripe.api_key = PAYMENT_SETTINGS['STRIPE_SECRET_KEY']
        return stripe

    def initiate(self, transaction) -> dict:
        import stripe

        stripe.api_key = PAYMENT_SETTINGS['STRIPE_SECRET_KEY']
        order = transaction.order
        line_items = [
            {
                'price_data': {
                    'currency': transaction.currency.lower(),
                    'product_data': {
                        'name': item.product_name
                        + (f' - {item.variant_name}' if item.variant_name else ''),
                    },
                    'unit_amount': int(item.unit_price * 100),
                },
                'quantity': item.quantity,
            }
            for item in order.items.all()
        ]
        # Add tax and shipping as line items so Stripe total == order total.
        extras = [
            ('Shipping', order.shipping_fee),
            ('Tax', order.tax),
        ]
        if order.discount and order.discount > 0:
            line_items.append({
                'price_data': {
                    'currency': transaction.currency.lower(),
                    'product_data': {'name': 'Discount'},
                    'unit_amount': -int(order.discount * 100),
                },
                'quantity': 1,
            })
        for label, amount in extras:
            if amount and amount > 0:
                line_items.append({
                    'price_data': {
                        'currency': transaction.currency.lower(),
                        'product_data': {'name': label},
                        'unit_amount': int(amount * 100),
                    },
                    'quantity': 1,
                })
        session = stripe.checkout.Session.create(
            mode='payment',
            client_reference_id=transaction.reference,
            line_items=line_items,
            success_url=_absolute_url(
                self.request,
                reverse('payments:verify', kwargs={'reference': transaction.reference}),
            ) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=_absolute_url(
                self.request,
                reverse('payments:cancel', kwargs={'reference': transaction.reference}),
            ),
            customer_email=order.email,
        )
        transaction.transaction_id = session.id
        transaction.status = 'pending'
        transaction.gateway_response = {'session_id': session.id, 'url': session.url}
        transaction.save(update_fields=['transaction_id', 'status', 'gateway_response', 'updated_at'])
        return {'redirect_url': session.url}

    def verify(self, transaction, data: dict) -> tuple[bool, str | None]:
        stripe = self._client()
        session_id = data.get('session_id') or transaction.transaction_id
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception as exc:
            return False, f'Stripe verification failed: {exc}'
        transaction.gateway_response = {**transaction.gateway_response, 'session': session.id}
        transaction.save(update_fields=['gateway_response', 'updated_at'])
        if session.payment_status == 'paid':
            return True, None
        return False, f'Stripe reports payment status: {session.payment_status}'

    def handle_webhook(self, payload: bytes, headers: dict) -> tuple[str | None, bool]:
        stripe = self._client()
        secret = PAYMENT_SETTINGS.get('STRIPE_WEBHOOK_SECRET')
        signature = headers.get('Stripe-Signature', '')
        try:
            if secret:
                event = stripe.Webhook.construct_event(payload, signature, secret)
            else:  # local/dev mode without a configured endpoint secret
                import json

                event = json.loads(payload)
        except Exception:
            return None, False
        if event.get('type') == 'checkout.session.completed':
            session = event.get('data', {}).get('object', {})
            return session.get('client_reference_id'), True
        return None, False


class RazorpayGateway(BaseGateway):
    """Razorpay Orders flow with server-side signature verification."""

    code = 'razorpay'
    label = 'UPI / Cards / Netbanking (Razorpay)'
    description = 'Pay securely via Razorpay.'

    @classmethod
    def is_available(cls) -> bool:
        try:
            import razorpay  # noqa: F401
        except ImportError:
            return False
        return bool(PAYMENT_SETTINGS.get('RAZORPAY_KEY_ID')
                    and PAYMENT_SETTINGS.get('RAZORPAY_KEY_SECRET'))

    def _client(self):
        import razorpay

        return razorpay.Client(
            auth=(PAYMENT_SETTINGS['RAZORPAY_KEY_ID'], PAYMENT_SETTINGS['RAZORPAY_KEY_SECRET']),
        )

    def initiate(self, transaction) -> dict:
        client = self._client()
        order = transaction.order
        rzp_order = client.order.create({
            'amount': int(transaction.amount * 100),
            'currency': transaction.currency,
            'receipt': transaction.reference,
            'notes': {'order_number': order.order_number},
        })
        transaction.transaction_id = rzp_order['id']
        transaction.status = 'pending'
        transaction.gateway_response = {'razorpay_order_id': rzp_order['id']}
        transaction.save(update_fields=['transaction_id', 'status', 'gateway_response', 'updated_at'])
        return {
            'template': 'payments/razorpay_checkout.html',
            'context': {
                'transaction': transaction,
                'order': order,
                'razorpay_key_id': PAYMENT_SETTINGS['RAZORPAY_KEY_ID'],
                'razorpay_order_id': rzp_order['id'],
                'amount_paise': int(transaction.amount * 100),
            },
        }

    def verify(self, transaction, data: dict) -> tuple[bool, str | None]:
        secret = PAYMENT_SETTINGS['RAZORPAY_KEY_SECRET']
        order_id = data.get('razorpay_order_id') or transaction.transaction_id
        payment_id = data.get('razorpay_payment_id', '')
        signature = data.get('razorpay_signature', '')
        expected = hmac.new(
            secret.encode(), f'{order_id}|{payment_id}'.encode(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False, 'Razorpay signature verification failed.'
        transaction.transaction_id = payment_id
        transaction.gateway_response = {
            **transaction.gateway_response,
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
        }
        transaction.save(update_fields=['transaction_id', 'gateway_response', 'updated_at'])
        return True, None

    def handle_webhook(self, payload: bytes, headers: dict) -> tuple[str | None, bool]:
        secret = PAYMENT_SETTINGS.get('RAZORPAY_WEBHOOK_SECRET')
        signature = headers.get('X-Razorpay-Signature', '')
        if secret:
            expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return None, False
        import json

        try:
            event = json.loads(payload)
        except ValueError:
            return None, False
        if event.get('event') == 'payment.captured':
            entity = event.get('payload', {}).get('payment', {}).get('entity', {})
            receipt = entity.get('receipt')
            return receipt, True
        return None, False


GATEWAYS: dict[str, type[BaseGateway]] = {
    SimulatedGateway.code: SimulatedGateway,
    StripeGateway.code: StripeGateway,
    RazorpayGateway.code: RazorpayGateway,
}


def get_gateway(code: str, request=None) -> BaseGateway:
    """Instantiate a gateway by code; raises GatewayError when unknown."""
    gateway_cls = GATEWAYS.get(code)
    if gateway_cls is None:
        raise GatewayError(f'Unknown payment gateway "{code}".')
    return gateway_cls(request=request)


def available_gateways(request=None) -> list[BaseGateway]:
    """All configured gateways, in a stable, customer-friendly order."""
    ordered = ['razorpay', 'stripe', 'simulated']
    found = []
    for code in ordered:
        gateway_cls = GATEWAYS[code]
        if gateway_cls.is_available():
            found.append(gateway_cls(request=request))
    return found
