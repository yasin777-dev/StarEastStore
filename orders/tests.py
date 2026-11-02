"""Order, checkout and totals tests (section 8)."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Address
from products.models import Category, Product

from .models import Order, OrderStatus, PaymentStatus, ShippingMethod
from .services import CheckoutError, compute_totals, place_order

User = get_user_model()


class TotalsTests(TestCase):
    def test_totals_without_extras(self):
        totals = compute_totals(Decimal('100.00'))
        self.assertEqual(totals.total, Decimal('100.00'))
        self.assertEqual(totals.discount, Decimal('0.00'))

    def test_totals_with_discount_and_shipping(self):
        method = ShippingMethod.objects.create(name='Standard', price=Decimal('4.99'))
        # 30 - 5 = 25 discounted subtotal, below the free-shipping threshold.
        totals = compute_totals(Decimal('30.00'), method, discount=Decimal('5'))
        self.assertEqual(totals.discount, Decimal('5.00'))
        self.assertEqual(totals.shipping_fee, Decimal('4.99'))
        self.assertEqual(totals.total, Decimal('29.99'))

    def test_free_shipping_threshold(self):
        method = ShippingMethod.objects.create(name='Std', price=Decimal('4.99'))
        totals = compute_totals(Decimal('100.00'), method)  # threshold 75
        self.assertEqual(totals.shipping_fee, Decimal('0.00'))
        totals = compute_totals(Decimal('30.00'), method)
        self.assertEqual(totals.shipping_fee, Decimal('4.99'))


class PlaceOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('buyer@example.com', 'x1A!aaaa')
        self.address = Address.objects.create(
            user=self.user, full_name='Buyer', phone='5551234567',
            address_line_1='1 Main', city='Town', state='TS',
            postal_code='12345', country='USA',
        )
        self.shipping = ShippingMethod.objects.create(
            name='Standard', price=Decimal('4.99'),
        )
        self.product = Product.objects.create(
            name='Order Widget', sku='OW-1',
            category=Category.objects.create(name='Order Cat'),
            description='Orderable', price=Decimal('40.00'), stock_quantity=10,
        )
        from cart.services import DatabaseCart

        self.cart = DatabaseCart(self.user)

    def _add(self, qty=2):
        self.cart.add(self.product, None, qty)

    def test_place_order_creates_snapshot(self):
        self._add(2)
        order = place_order(
            user=self.user, cart=self.cart, address=self.address,
            shipping_method_id=self.shipping.pk, payment_method='cod',
        )
        item = order.items.first()
        self.assertEqual(item.product_name, 'Order Widget')
        self.assertEqual(item.sku, 'OW-1')
        self.assertEqual(item.unit_price, Decimal('40.00'))
        self.assertEqual(order.subtotal, Decimal('80.00'))
        # Subtotal >= FREE_SHIPPING_THRESHOLD (75) -> shipping is free.
        self.assertEqual(order.shipping_fee, Decimal('0.00'))
        self.assertEqual(order.total, Decimal('80.00'))
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_place_order_clears_cart(self):
        self._add(1)
        place_order(user=self.user, cart=self.cart, address=self.address,
                    shipping_method_id=self.shipping.pk, payment_method='cod')
        self.assertTrue(self.cart.is_empty())

    def test_place_order_rejects_empty_cart(self):
        with self.assertRaises(CheckoutError):
            place_order(user=self.user, cart=self.cart, address=self.address,
                        shipping_method_id=None, payment_method='cod')

    def test_place_order_validates_stock(self):
        self._add(20)  # cart service clamps to stock... force the line:
        from cart.models import CartItem

        CartItem.objects.filter(cart=self.cart.cart).update(quantity=20)
        with self.assertRaises(CheckoutError):
            place_order(user=self.user, cart=self.cart, address=self.address,
                        shipping_method_id=None, payment_method='cod')

    def test_order_number_format_unique(self):
        self._add(1)
        order1 = place_order(user=self.user, cart=self.cart, address=self.address,
                             shipping_method_id=None, payment_method='cod')
        self.cart.add(self.product, None, 1)
        order2 = place_order(user=self.user, cart=self.cart, address=self.address,
                             shipping_method_id=None, payment_method='cod')
        self.assertTrue(order1.order_number.startswith('ORD-'))
        self.assertNotEqual(order1.order_number, order2.order_number)


class CheckoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('ck@example.com', 'x1A!aaaa')
        self.address = Address.objects.create(
            user=self.user, full_name='Ck', phone='5551234567',
            address_line_1='2 Side St', city='Town', state='TS',
            postal_code='12345', country='USA',
        )
        self.shipping = ShippingMethod.objects.create(name='Standard', price=Decimal('4.99'))
        self.product = Product.objects.create(
            name='Checkout Widget', sku='CK-1',
            category=Category.objects.create(name='Checkout Cat'),
            description='Checkoutable', price=Decimal('30.00'), stock_quantity=8,
        )

    def test_checkout_requires_login(self):
        response = self.client.get(reverse('orders:checkout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_checkout_empty_cart_redirects(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('orders:checkout'))
        self.assertRedirects(response, reverse('products:list'))

    def test_full_cod_checkout_reduces_stock_and_confirms(self):
        from cart.services import DatabaseCart

        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 2)
        response = self.client.post(reverse('orders:checkout'), {
            'address_id': self.address.pk, 'shipping_method': self.shipping.pk,
            'payment_method': 'cod', 'customer_note': 'ring twice',
            'action': 'place_order',
        })
        order = Order.objects.get(user=self.user)
        self.assertRedirects(
            response, f'{order.get_absolute_url()}?placed=1')
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, PaymentStatus.COD_PENDING)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)
        self.assertEqual(len(mail.outbox), 2)  # order + payment confirmation

    def test_order_detail_owner_only(self):
        from cart.services import DatabaseCart

        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 1)
        self.client.post(reverse('orders:checkout'), {
            'address_id': self.address.pk, 'shipping_method': self.shipping.pk,
            'payment_method': 'cod', 'action': 'place_order',
        })
        order = Order.objects.get(user=self.user)
        other = User.objects.create_user('intruder@example.com', 'x1A!aaaa')
        client2 = Client()
        client2.force_login(other)
        response = client2.get(
            reverse('orders:detail', kwargs={'order_number': order.order_number}))
        self.assertEqual(response.status_code, 404)

    def test_order_list_shows_only_own(self):
        from cart.services import DatabaseCart

        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 1)
        self.client.post(reverse('orders:checkout'), {
            'address_id': self.address.pk, 'shipping_method': self.shipping.pk,
            'payment_method': 'cod', 'action': 'place_order',
        })
        stranger = User.objects.create_user('stranger@example.com', 'x1A!aaaa')
        client2 = Client()
        client2.force_login(stranger)
        response = client2.get(reverse('orders:list'))
        self.assertNotContains(response, Order.objects.first().order_number)


class OrderCancellationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('cancel@example.com', 'x1A!aaaa')
        self.address = Address.objects.create(
            user=self.user, full_name='C', phone='5551234567',
            address_line_1='3 Elm', city='Town', state='TS',
            postal_code='12345', country='USA',
        )
        self.product = Product.objects.create(
            name='Cancel Widget', sku='CX-1',
            category=Category.objects.create(name='Cancel Cat'),
            description='Cancellable', price=Decimal('10.00'), stock_quantity=5,
        )

    def _place(self, payment_method='cod'):
        from cart.services import DatabaseCart

        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 2)
        self.client.post(reverse('orders:checkout'), {
            'address_id': self.address.pk, 'shipping_method': ShippingMethod.objects.create(
                name='Std', price=Decimal('2.00')).pk,
            'payment_method': payment_method, 'action': 'place_order',
        })
        return Order.objects.get(user=self.user)

    def test_cancel_cod_restores_stock(self):
        order = self._place()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        response = self.client.post(
            reverse('orders:cancel', kwargs={'order_number': order.order_number}))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertFalse(order.stock_deducted)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_cannot_cancel_shipped_order(self):
        order = self._place()
        order.status = OrderStatus.SHIPPED
        order.save()
        response = self.client.post(
            reverse('orders:cancel', kwargs={'order_number': order.order_number}))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SHIPPED)

    def test_cannot_cancel_other_users_order(self):
        order = self._place()
        intruder = User.objects.create_user('evil@example.com', 'x1A!aaaa')
        client2 = Client()
        client2.force_login(intruder)
        response = client2.post(
            reverse('orders:cancel', kwargs={'order_number': order.order_number}))
        self.assertEqual(response.status_code, 404)


class CheckoutPreviewTests(TestCase):
    """The checkout page previews totals before the order is placed."""

    def setUp(self):
        from cart.services import DatabaseCart

        self.client = Client()
        self.user = User.objects.create_user('preview-ck@example.com', 'x1A!aaaa')
        self.address = Address.objects.create(
            user=self.user, full_name='Preview Customer', phone='5551234567',
            address_line_1='4 Preview Rd', city='Town', state='TS',
            postal_code='12345', country='India',
        )
        self.shipping = ShippingMethod.objects.create(
            name='Courier', price=Decimal('4.99'),
        )
        self.product = Product.objects.create(
            name='Preview Widget', sku='PV-1',
            category=Category.objects.create(name='Preview Cat'),
            description='Previewable', price=Decimal('30.00'), stock_quantity=10,
        )
        self.cart = DatabaseCart(self.user)
        self.client.force_login(self.user)

    def test_preview_total_includes_shipping(self):
        self.cart.add(self.product, None, 1)  # 30.00 + 4.99 = 34.99
        response = self.client.get(reverse('orders:checkout'))
        self.assertContains(
            response, f'Place order · {settings.CURRENCY}34.99',
        )
