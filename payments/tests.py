"""Payment flow tests: simulated gateway, idempotency, COD, inventory."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from cart.services import DatabaseCart
from orders.models import Coupon, Order, OrderStatus, ShippingMethod
from products.models import Category, Product

from .gateways import GatewayError, get_gateway
from .services import verify_and_complete

User = get_user_model()


class GatewayRegistryTests(TestCase):
    def test_unknown_gateway_raises(self):
        with self.assertRaises(GatewayError):
            get_gateway('not-a-gateway')

    @override_settings(SIMULATED_GATEWAY_ENABLED=True)
    def test_simulated_available_in_dev(self):
        from .gateways import available_gateways, SimulatedGateway

        gateways = available_gateways()
        self.assertIn(SimulatedGateway, [type(g) for g in gateways])

    @override_settings(SIMULATED_GATEWAY_ENABLED=False)
    def test_simulated_hidden_when_disabled(self):
        from .gateways import available_gateways, SimulatedGateway

        gateways = available_gateways()
        self.assertNotIn(SimulatedGateway, [type(g) for g in gateways])


class PaymentFlowTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.shipping = ShippingMethod.objects.create(
            name='Standard', price=Decimal('4.99'))
        cls.category = Category.objects.create(name='Pay Cat')

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('payer@example.com', 'x1A!aaaa')
        self.address = Address.objects.create(
            user=self.user, full_name='Payer', phone='5551234567',
            address_line_1='4 Oak', city='Town', state='TS',
            postal_code='12345', country='USA',
        )
        self.product = Product.objects.create(
            name='Pay Widget', sku='PW-1', category=self.category,
            description='Payable', price=Decimal('25.00'), stock_quantity=10,
        )

    def _login(self):
        self.client.force_login(self.user)

    def _add_to_cart(self, qty=2):
        DatabaseCart(self.user).add(self.product, None, qty)

    def _place_order(self, payment_method='simulated', coupon_code=''):
        self._login()
        self._add_to_cart()
        response = self.client.post(reverse('orders:checkout'), {
            'address_id': self.address.pk, 'shipping_method': self.shipping.pk,
            'payment_method': payment_method, 'coupon_code': coupon_code,
            'action': 'place_order',
        })
        assert response.status_code == 302, response.content[:400]
        return Order.objects.get(user=self.user)


@override_settings(SIMULATED_GATEWAY_ENABLED=True)
class SimulatedGatewayFlowTests(PaymentFlowTestBase):
    def test_successful_payment_completes_order(self):
        order = self._place_order('simulated')
        self.assertEqual(order.status, OrderStatus.PENDING)
        txn = order.transactions.latest('created_at')
        response = self.client.post(
            reverse('payments:simulate_process', kwargs={'reference': txn.reference}),
            {'outcome': 'success'})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, 'paid')
        self.assertTrue(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertRedirects(
            response, f'{order.get_absolute_url()}?placed=1')

    def test_failed_payment_keeps_order_pending(self):
        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        self.client.post(
            reverse('payments:simulate_process', kwargs={'reference': txn.reference}),
            {'outcome': 'failure'})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, 'pending')
        self.assertFalse(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'failed')

    def test_cancelled_payment_can_be_retried(self):
        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        self.client.post(
            reverse('payments:simulate_process', kwargs={'reference': txn.reference}),
            {'outcome': 'cancel'})
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'cancelled')
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_verification_is_idempotent(self):
        """Double verification (browser + webhook) must not double-charge."""
        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        first = verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        second = verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        self.assertEqual(first.pk, second.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)  # deducted exactly once

    def test_coupon_marked_used_exactly_once(self):
        coupon = Coupon.objects.create(
            code='PAY10', discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10'), minimum_order_amount=Decimal('10'),
        )
        order = self._place_order('simulated', coupon_code='PAY10')
        self.assertIsNotNone(order.coupon)
        txn = order.transactions.latest('created_at')
        verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        # Webhook-style duplicate call:
        verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_stock_race_is_guarded(self):
        """verify_and_complete refuses to oversell when stock ran out."""
        order = self._place_order('simulated')
        # Someone else buys the remaining stock in the meantime.
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=0)
        txn = order.transactions.latest('created_at')
        verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        order.refresh_from_db()
        # Payment captured, but the order is NOT confirmed or oversold.
        self.assertEqual(order.payment_status, 'paid')
        self.assertNotEqual(order.status, OrderStatus.CONFIRMED)
        self.assertFalse(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertTrue(
            order.status_updates.filter(note__icontains='Stock unavailable').exists())

    def test_cannot_pay_someone_elses_transaction(self):
        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        intruder = User.objects.create_user('hacker@example.com', 'x1A!aaaa')
        client2 = Client()
        client2.force_login(intruder)
        response = client2.post(
            reverse('payments:simulate_process', kwargs={'reference': txn.reference}),
            {'outcome': 'success'})
        self.assertIn(response.status_code, (302, 403))
        # Redirected away without completing the payment.
        txn.refresh_from_db()
        self.assertNotEqual(txn.status, 'succeeded')

    def test_payment_confirmation_email_sent(self):
        from django.core import mail

        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any('Payment received' in s for s in subjects))
        self.assertTrue(any('confirmed' in s for s in subjects))


class CashOnDeliveryTests(PaymentFlowTestBase):
    def test_cod_confirms_and_deducts(self):
        order = self._place_order('cod')
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, 'cod_pending')
        self.assertTrue(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

    def test_cod_is_idempotent(self):
        from .services import confirm_cash_on_delivery

        order = self._place_order('cod')
        confirm_cash_on_delivery(order)
        confirm_cash_on_delivery(order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)


class RefundTests(PaymentFlowTestBase):
    def test_paid_order_cancel_restores_stock_and_marks_refunded(self):
        order = self._place_order('simulated')
        txn = order.transactions.latest('created_at')
        verify_and_complete(txn.reference, 'simulated', {'outcome': 'success'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

        self.client.post(
            reverse('orders:cancel', kwargs={'order_number': order.order_number}))
        order.refresh_from_db()
        txn.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(order.payment_status, 'refunded')
        self.assertEqual(txn.status, 'refunded')
        self.assertFalse(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)


class StripeGatewayConfigTests(TestCase):
    def test_stripe_unavailable_without_keys(self):
        from .gateways import StripeGateway

        self.assertFalse(StripeGateway.is_available())

    def test_razorpay_unavailable_without_keys(self):
        from .gateways import RazorpayGateway

        self.assertFalse(RazorpayGateway.is_available())

    def test_webhook_unknown_gateway_rejected(self):
        response = self.client.post(reverse('payments:webhook',
                                            kwargs={'gateway_code': 'bogus'}),
                                    data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_webhook_invalid_payload_rejected_for_simulated(self):
        # Simulated gateway has no webhook implementation.
        response = self.client.post(reverse('payments:webhook',
                                            kwargs={'gateway_code': 'simulated'}),
                                    data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
