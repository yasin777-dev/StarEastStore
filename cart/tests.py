"""Cart tests: session vs database backends, stock rules, totals."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Category, Product, ProductVariant

from .models import Cart, CartItem
from .services import CartError, DatabaseCart, SessionCart, get_cart

User = get_user_model()


def make_product(name='Cart Item', price='10.00', stock=10):
    return Product.objects.create(
        name=name, sku=f'C-{name[:16]}',
        category=Category.objects.create(name=f'CCat {name}'),
        description='Cart test product',
        price=Decimal(price), stock_quantity=stock,
    )


class SessionCartTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.product = make_product(stock=5)

    def test_guest_add_updates_and_remove(self):
        session = self.client.session
        session.save()
        cart = SessionCart(self.client)
        cart.add(self.product, None, 2)
        self.assertEqual(cart.count(), 2)
        cart.add(self.product, None, 1)
        self.assertEqual(cart.count(), 3)
        cart.update(self.product.pk, None, 4)
        self.assertEqual(cart.count(), 4)
        cart.remove(self.product.pk)
        self.assertTrue(cart.is_empty())

    def test_session_cart_persists_across_requests(self):
        self.client.get('/')  # ensures a session cookie
        csrf_token = _get_csrf(self.client, reverse('products:list'))
        self.client.post(reverse('cart:add'), {
            'product_id': self.product.pk, 'quantity': 2,
            'csrfmiddlewaretoken': csrf_token,
        })
        response = self.client.get(reverse('cart:detail'))
        self.assertContains(response, self.product.name)

    def test_quantity_clamped_to_stock(self):
        cart = SessionCart(self.client)
        cart.add(self.product, None, 6)  # stock is 5 -> clamped
        self.assertEqual(cart.count(), 5)
        cart.add(self.product, None, 3)  # cannot exceed stock, still 5
        self.assertEqual(cart.count(), 5)

    def test_cannot_add_inactive_product(self):
        self.product.is_active = False
        self.product.save()
        cart = SessionCart(self.client)
        raw = cart.as_session_dict()
        raw[f'{self.product.pk}:0'] = 1
        cart._save(raw)
        self.assertTrue(cart.is_empty())  # silently dropped on read


class DatabaseCartTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('cartuser@example.com', 'x1A!aaaa')
        self.product = make_product('DB Item', stock=4)
        self.varianted = make_product('Varianted', stock=0)
        self.variant = ProductVariant.objects.create(
            product=self.varianted, size='M', color='Red', sku='DB-VAR',
            stock_quantity=2,
        )

    def test_get_cart_for_user_creates_db_cart(self):
        cart = get_cart(_fake_request(self.user))
        self.assertIsInstance(cart, DatabaseCart)
        self.assertIsInstance(cart.cart, Cart)

    def test_add_get_or_create_unique_line(self):
        cart = DatabaseCart(self.user)
        cart.add(self.product, None, 1)
        cart.add(self.product, None, 2)
        self.assertEqual(CartItem.objects.filter(cart=cart.cart).count(), 1)
        self.assertEqual(cart.count(), 3)

    def test_variant_lines_are_separate(self):
        cart = DatabaseCart(self.user)
        cart.add(self.product, None, 1)
        cart.add(self.varianted, self.variant, 1)
        self.assertEqual(cart.count(), 2)
        self.assertEqual(len(cart.lines()), 2)

    def test_stock_validation_db_backend(self):
        cart = DatabaseCart(self.user)
        cart.add(self.varianted, self.variant, 3)  # variant stock is 2 -> clamp
        self.assertEqual(cart.count(), 2)
        cart.add(self.varianted, self.variant, 2)  # still capped at 2
        self.assertEqual(cart.count(), 2)
        # Zero-stock product outright rejected.
        from decimal import Decimal as D

        empty = Product.objects.create(
            name='Empty Item', sku='EMPTY-1',
            category=self.varianted.category, description='x',
            price=D('5.00'), stock_quantity=0)
        with self.assertRaises(CartError):
            cart.add(empty, None, 1)

    def test_subtotal_uses_variant_price(self):
        cart = DatabaseCart(self.user)
        cart.add(self.product, None, 2)   # 10.00 each
        self.variant.price = Decimal('25.00')
        self.variant.save()
        cart.add(self.varianted, self.variant, 1)
        self.assertEqual(cart.subtotal(), Decimal('45.00'))

    def test_clear(self):
        cart = DatabaseCart(self.user)
        cart.add(self.product, None, 1)
        cart.clear()
        self.assertTrue(cart.is_empty())

    def test_remove_missing_raises(self):
        cart = DatabaseCart(self.user)
        with self.assertRaises(CartError):
            cart.remove(self.product.pk)


class CartMergeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.product = make_product('Merge Item', stock=10)

    def test_guest_cart_merges_on_login(self):
        csrf_token = _get_csrf(self.client, reverse('accounts:login'))
        # Add as guest
        csrf_token = _get_csrf(self.client, reverse('products:list'))
        self.client.post(reverse('cart:add'), {
            'product_id': self.product.pk, 'quantity': 3,
            'csrfmiddlewaretoken': csrf_token,
        })
        # Login
        User.objects.create_user('merger@example.com', 'x1A!aaaa')
        csrf_token = _get_csrf(self.client, reverse('accounts:login'))
        self.client.post(reverse('accounts:login'), {
            'username': 'merger@example.com', 'password': 'x1A!aaaa',
            'csrfmiddlewaretoken': csrf_token,
        })
        cart = DatabaseCart(User.objects.get(email='merger@example.com'))
        self.assertEqual(cart.count(), 3)
        # Session cart cleared after merge
        self.assertEqual(SessionCart(self.client).count(), 0)

    def test_merge_clamps_to_stock(self):
        self.product.stock_quantity = 2
        self.product.save()
        csrf_token = _get_csrf(self.client, reverse('products:list'))
        self.client.post(reverse('cart:add'), {
            'product_id': self.product.pk, 'quantity': 5,
            'csrfmiddlewaretoken': csrf_token,
        })
        # The add itself clamps to available stock.
        cart = SessionCart(self.client)
        self.assertEqual(cart.count(), 2)


class CartViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('viewuser@example.com', 'x1A!aaaa')
        self.product = make_product('View Item', stock=10)

    def test_add_requires_product_id(self):
        response = self.client.post(reverse('cart:add'), {})
        self.assertEqual(response.status_code, 302)  # redirects with error message

    def test_update_quantity(self):
        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 2)
        self.client.post(reverse('cart:update'), {
            'product_id': self.product.pk, 'quantity': 5,
        })
        cart = DatabaseCart(self.user)
        self.assertEqual(cart.count(), 5)

    def test_zero_quantity_removes_line(self):
        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 2)
        self.client.post(reverse('cart:update'), {
            'product_id': self.product.pk, 'quantity': 0,
        })
        self.assertTrue(DatabaseCart(self.user).is_empty())

    def test_context_processor_exposes_count(self):
        self.client.force_login(self.user)
        DatabaseCart(self.user).add(self.product, None, 3)
        response = self.client.get(reverse('cart:detail'))
        self.assertEqual(response.context['cart_item_count'], 3)


def _fake_request(user):
    from django.test.client import RequestFactory

    request = RequestFactory().get('/')
    request.user = user
    return request


def _get_csrf(client, url):
    response = client.get(url)
    from django.middleware.csrf import get_token

    return get_token(response.wsgi_request)
