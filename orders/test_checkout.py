"""Checkout persistence, admin visibility and customer confirmation regressions."""
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from cart.services import CartError, DatabaseCart
from payments.gateways import GatewayError
from products.models import Category, Product

from .models import Order, OrderItem, OrderStatus, OrderStatusUpdate, PaymentStatus, ShippingMethod

User = get_user_model()


class CheckoutPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('checkout@example.com')
        cls.admin = User.objects.create_superuser('orders-admin@example.com')
        cls.address = Address.objects.create(
            user=cls.user, full_name='Checkout Customer', phone='9876543210',
            address_line_1='12 Market Road', city='Surat', state='Gujarat',
            postal_code='395001', country='India',
        )
        cls.shipping = ShippingMethod.objects.create(name='Courier', price=Decimal('4.99'))
        cls.product = Product.objects.create(
            name='Checkout product', sku='CHECKOUT-PERSIST',
            category=Category.objects.create(name='Checkout products'),
            description='Checkout regression product', price=Decimal('30.00'),
            stock_quantity=8,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.cart = DatabaseCart(self.user)
        self.cart.add(self.product, None, 2)
        self.payload = {
            'address_id': self.address.pk,
            'shipping_method': self.shipping.pk,
            'payment_method': 'cod',
            'customer_note': 'Please ring the bell.',
            'action': 'place_order',
        }

    def assert_visible_in_admin(self, order):
        admin_client = Client()
        admin_client.force_login(self.admin)
        for url in (
            reverse('admin:index'),
            reverse('admin:orders_order_changelist'),
            reverse('admin:orders_order_change', args=[order.pk]),
        ):
            with self.subTest(url=url):
                response = admin_client.get(url)
                self.assertContains(response, order.order_number)
                self.assertContains(response, self.user.email)
        detail = admin_client.get(reverse('admin:orders_order_change', args=[order.pk]))
        self.assertContains(detail, self.product.sku)

    def test_cod_order_persisted_with_items_and_visible_in_admin(self):
        response = self.client.post(reverse('orders:checkout'), self.payload, follow=True)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, PaymentStatus.COD_PENDING)
        self.assertEqual(order.shipping_full_name, self.address.full_name)
        self.assertEqual(order.shipping_address_line_1, self.address.address_line_1)
        self.assertEqual(order.shipping_city, 'Surat')
        self.assertEqual(order.customer_note, self.payload['customer_note'])
        self.assertEqual(order.total, Decimal('64.99'))
        item = order.items.get()
        self.assertEqual((item.product_id, item.quantity), (self.product.pk, 2))
        self.assertEqual(item.total_price, Decimal('60.00'))
        self.assertEqual(order.status_updates.count(), 2)
        self.assertTrue(self.cart.is_empty())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)
        self.assertContains(response, 'Your order has been placed successfully!')
        self.assertContains(response, 'id="orderSuccessModal"')
        self.assertContains(response, reverse('products:list'))
        self.assertContains(self.client.get(reverse('orders:list')), order.order_number)
        self.assert_visible_in_admin(order)

    def test_invalid_fields_are_visible_and_do_not_create_an_order(self):
        self.payload.update(shipping_method='', payment_method='unknown', customer_note='x' * 501)
        response = self.client.post(reverse('orders:checkout'), self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your order has not been placed yet')
        self.assertContains(response, 'Please select a shipping method.')
        self.assertContains(response, 'Please select an available payment method.')
        self.assertContains(response, 'at most 500 characters')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.cart.count(), 2)
        self.assertNotContains(response, 'id="orderSuccessModal"')

    def test_unavailable_shipping_is_explicit_and_does_not_allow_free_checkout(self):
        ShippingMethod.objects.update(is_active=False)
        response = self.client.get(reverse('orders:checkout'))
        self.assertContains(response, 'Shipping is currently unavailable')
        response = self.client.post(reverse('orders:checkout'), self.payload)
        self.assertContains(response, 'Shipping is currently unavailable')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.cart.count(), 2)

    def test_another_customers_address_cannot_be_used(self):
        other = User.objects.create_user('other-address@example.com')
        self.address.user = other
        self.address.save()
        response = self.client.post(reverse('orders:checkout'), self.payload)
        self.assertContains(response, 'Please select one of your saved shipping addresses.')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.cart.count(), 2)

    def test_cod_stock_failure_rolls_back_order_and_keeps_cart(self):
        with patch('orders.services.reduce_order_stock', side_effect=CartError('Insufficient stock.')):
            response = self.client.post(reverse('orders:checkout'), self.payload)
        self.assertContains(response, 'Insufficient stock.')
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertFalse(OrderStatusUpdate.objects.exists())
        self.assertEqual(self.cart.count(), 2)
        self.assertNotContains(response, 'id="orderSuccessModal"')

    def test_confirmation_is_shown_once_and_cannot_be_replayed_with_query_string(self):
        response = self.client.post(reverse('orders:checkout'), self.payload)
        first_visit = self.client.get(response.url)
        self.assertTrue(first_visit.context['just_placed'])
        self.assertContains(first_visit, 'id="orderSuccessModal"')
        refresh = self.client.get(response.url)
        self.assertFalse(refresh.context['just_placed'])
        self.assertNotContains(refresh, 'id="orderSuccessModal"')

    def test_resubmitting_checkout_does_not_duplicate_order(self):
        self.client.post(reverse('orders:checkout'), self.payload)
        self.client.post(reverse('orders:checkout'), self.payload)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)

    @override_settings(SIMULATED_GATEWAY_ENABLED=True)
    def test_gateway_failure_preserves_pending_order_and_offers_retry(self):
        self.payload['payment_method'] = 'simulated'
        with patch('payments.gateways.SimulatedGateway.initiate', side_effect=GatewayError('Unavailable')):
            response = self.client.post(reverse('orders:checkout'), self.payload, follow=True)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)
        self.assertEqual(order.items.count(), 1)
        self.assertContains(response, 'Your order is saved')
        self.assertContains(response, 'Retry payment')
        self.assertContains(response, f'action="{reverse("payments:retry", args=[order.order_number])}"')
        self.assertNotContains(response, 'id="orderSuccessModal"')
        self.assertEqual(order.transactions.get().status, 'failed')
        self.assert_visible_in_admin(order)
        retry = self.client.post(reverse('payments:retry', args=[order.order_number]))
        self.assertEqual(retry.status_code, 302)
        self.assertIn('/payment/simulate/', retry.url)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(order.transactions.count(), 2)

    @override_settings(SIMULATED_GATEWAY_ENABLED=True)
    def test_online_order_is_saved_before_payment_and_only_confirmed_after_verification(self):
        self.payload['payment_method'] = 'simulated'
        self.client.post(reverse('orders:checkout'), self.payload)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, OrderStatus.PENDING)
        pending = self.client.get(f'{order.get_absolute_url()}?placed=1')
        self.assertFalse(pending.context['just_placed'])
        self.assertNotContains(pending, 'id="orderSuccessModal"')
        self.assert_visible_in_admin(order)

        txn = order.transactions.get()
        response = self.client.post(
            reverse('payments:simulate_process', args=[txn.reference]),
            {'outcome': 'success'}, follow=True,
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertContains(response, 'id="orderSuccessModal"')
        self.assertContains(response, 'Your order has been placed successfully!')

    @override_settings(SIMULATED_GATEWAY_ENABLED=True)
    def test_failed_payment_never_shows_order_success_popup(self):
        self.payload['payment_method'] = 'simulated'
        self.client.post(reverse('orders:checkout'), self.payload)
        order = Order.objects.get(user=self.user)
        txn = order.transactions.get()
        response = self.client.post(
            reverse('payments:simulate_process', args=[txn.reference]),
            {'outcome': 'failure'}, follow=True,
        )
        self.assertFalse(response.context['just_placed'])
        self.assertNotContains(response, 'id="orderSuccessModal"')
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())


class ShippingSetupTests(TestCase):
    @staticmethod
    def ensure_shipping():
        migration = import_module('orders.migrations.0003_default_shipping_method')
        migration.ensure_default_shipping_method(apps, SimpleNamespace(connection=connection))

    def test_migrate_provisions_shipping_without_demo_seed_data(self):
        self.assertTrue(ShippingMethod.objects.filter(name='Standard shipping', is_active=True).exists())

    def test_empty_store_gets_existing_standard_rate_once(self):
        ShippingMethod.objects.all().delete()
        self.ensure_shipping()
        self.ensure_shipping()
        shipping = ShippingMethod.objects.get()
        self.assertEqual(shipping.name, 'Standard shipping')
        self.assertEqual(shipping.price, Decimal('4.99'))
        self.assertTrue(shipping.is_active)

    def test_existing_custom_or_disabled_shipping_is_never_overwritten(self):
        ShippingMethod.objects.all().delete()
        shipping = ShippingMethod.objects.create(
            name='Custom courier', price=Decimal('80.00'), is_active=False,
        )
        self.ensure_shipping()
        shipping.refresh_from_db()
        self.assertEqual(ShippingMethod.objects.count(), 1)
        self.assertEqual(shipping.price, Decimal('80.00'))
        self.assertFalse(shipping.is_active)
