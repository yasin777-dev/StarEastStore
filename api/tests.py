"""REST API tests (section 17)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Brand, Category, Product, ProductVariant

User = get_user_model()


class ApiTestBase(TestCase):
    def make_product(self, name='API Widget', price='30.00', stock=10, **kw):
        defaults = dict(
            sku=f'API-{name[:16]}',
            category=Category.objects.create(name=f'ACat {name}'),
            description='API product', price=Decimal(price),
            stock_quantity=stock,
        )
        defaults.update(kw)
        return Product.objects.create(name=name, **defaults)


class ProductApiTests(ApiTestBase):
    def test_product_list(self):
        product = self.make_product()
        response = self.client.get(reverse('api:product-list'))
        self.assertEqual(response.status_code, 200)
        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn(product.slug, slugs)

    def test_product_detail_with_variants(self):
        product = self.make_product(stock=0)
        ProductVariant.objects.create(
            product=product, size='L', color='Blue', sku='API-V1', stock_quantity=3)
        response = self.client.get(
            reverse('api:product-detail', kwargs={'slug': product.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['variants'][0]['sku'], 'API-V1')
        self.assertTrue(response.data['in_stock'])

    def test_product_filters(self):
        cheap = self.make_product('Cheap One', price='5.00')
        pricey = self.make_product('Pricey One', price='500.00')
        response = self.client.get(reverse('api:product-list'),
                                   {'max_price': '10'})
        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn(cheap.slug, slugs)
        self.assertNotIn(pricey.slug, slugs)

    def test_product_search_api(self):
        self.make_product('Unique Zephyr')
        response = self.client.get(reverse('api:product-list'), {'search': 'zephyr'})
        self.assertEqual(response.data['count'], 1)

    def test_category_and_brand_endpoints(self):
        category = Category.objects.create(name='API Cat')
        brand = Brand.objects.create(name='API Brand')
        self.make_product('Branded', category=category, brand=brand)
        response = self.client.get(reverse('api:category-detail',
                                           kwargs={'slug': category.slug}))
        self.assertEqual(response.data['product_count'], 1)
        response = self.client.get(reverse('api:brand-detail',
                                           kwargs={'slug': brand.slug}))
        self.assertEqual(response.data['product_count'], 1)


class CartApiTests(ApiTestBase):
    def setUp(self):
        self.client = Client()
        self.product = self.make_product(stock=5)

    def test_guest_cart_uses_session(self):
        response = self.client.post(reverse('api:api_cart'),
                                    {'product_id': self.product.pk, 'quantity': 2})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['count'], 2)
        # Same session sees the same cart.
        response = self.client.get(reverse('api:api_cart'))
        self.assertEqual(response.data['count'], 2)

    def test_add_more_than_stock_clamped(self):
        response = self.client.post(reverse('api:api_cart'),
                                    {'product_id': self.product.pk, 'quantity': 99})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['count'], 5)  # stock is 5

    def test_patch_and_delete(self):
        self.client.post(reverse('api:api_cart'),
                         {'product_id': self.product.pk, 'quantity': 2})
        response = self.client.patch(
            reverse('api:api_cart'), {'product_id': self.product.pk, 'quantity': 4},
            content_type='application/json')
        self.assertEqual(response.data['count'], 4)
        response = self.client.delete(reverse('api:api_cart'),
                                      {'product_id': self.product.pk},
                                      content_type='application/json')
        self.assertEqual(response.data['count'], 0)

    def test_cart_api_invalid_product_404(self):
        response = self.client.post(reverse('api:api_cart'),
                                    {'product_id': 999999})
        self.assertEqual(response.status_code, 404)


class WishlistApiTests(ApiTestBase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('apiwisher@example.com', 'x1A!aaaa')
        self.product = self.make_product()

    def test_requires_authentication(self):
        response = self.client.get(reverse('api:api_wishlist'))
        self.assertEqual(response.status_code, 403)

    def test_add_list_remove(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('api:api_wishlist'),
                                    {'product_id': self.product.pk})
        self.assertEqual(response.status_code, 201)
        # Duplicate add returns 200 (idempotent), not another row.
        response = self.client.post(reverse('api:api_wishlist'),
                                    {'product_id': self.product.pk})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('api:api_wishlist'))
        self.assertEqual(len(response.data), 1)
        response = self.client.delete(reverse('api:api_wishlist'),
                                      {'product_id': self.product.pk},
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)


class OrderApiTests(ApiTestBase):
    def test_orders_require_authentication(self):
        response = self.client.get(reverse('api:api_orders'))
        self.assertEqual(response.status_code, 403)

    def test_user_sees_only_own_orders(self):
        from accounts.models import Address
        from cart.services import DatabaseCart
        from orders.models import ShippingMethod

        user = User.objects.create_user('apiorder@example.com', 'x1A!aaaa')
        stranger = User.objects.create_user('apistranger@example.com', 'x1A!aaaa')
        Address.objects.create(user=user, full_name='A', phone='5551234567',
                               address_line_1='x', city='c', state='s',
                               postal_code='p', country='USA')
        shipping = ShippingMethod.objects.create(name='Std', price=Decimal('3.00'))
        product = self.make_product()
        DatabaseCart(user).add(product, None, 1)
        client = Client()
        client.force_login(user)
        client.post(reverse('orders:checkout'), {
            'address_id': Address.objects.get(user=user).pk,
            'shipping_method': shipping.pk, 'payment_method': 'cod',
            'action': 'place_order',
        })
        # Owner sees it.
        response = client.get(reverse('api:api_orders'))
        self.assertEqual(response.data['count'], 1)
        order_number = response.data['results'][0]['order_number']
        # Stranger does not.
        client2 = Client()
        client2.force_login(stranger)
        response = client2.get(reverse('api:api_orders'))
        self.assertEqual(response.data['count'], 0)
        response = client2.get(reverse('api:api_order_detail',
                                       kwargs={'order_number': order_number}))
        self.assertEqual(response.status_code, 404)

    def test_order_serializer_hides_private_data(self):
        from accounts.models import Address
        from cart.services import DatabaseCart
        from orders.models import ShippingMethod

        user = User.objects.create_user('apipayer@example.com', 'x1A!aaaa')
        Address.objects.create(user=user, full_name='A', phone='5551234567',
                               address_line_1='x', city='c', state='s',
                               postal_code='p', country='USA')
        shipping = ShippingMethod.objects.create(name='Std', price=Decimal('3.00'))
        product = self.make_product()
        DatabaseCart(user).add(product, None, 1)
        client = Client()
        client.force_login(user)
        client.post(reverse('orders:checkout'), {
            'address_id': Address.objects.get(user=user).pk,
            'shipping_method': shipping.pk, 'payment_method': 'cod',
            'action': 'place_order',
        })
        response = client.get(reverse('api:api_orders'))
        order_data = response.data['results'][0]
        self.assertNotIn('email', order_data)
        self.assertNotIn('user', order_data)


class ReviewApiTests(ApiTestBase):
    def setUp(self):
        self.user = User.objects.create_user('apirev@example.com', 'x1A!aaaa')
        self.product = self.make_product('Reviewed API Item')

    def test_reviews_are_public(self):
        from reviews.models import Review

        Review.objects.create(product=self.product, user=self.user,
                              rating=5, title='Nice', text='Nice product indeed.')
        response = self.client.get(
            reverse('api:api_product_reviews', kwargs={'slug': self.product.slug}))
        self.assertEqual(response.data['rating']['count'], 1)
        self.assertEqual(response.data['results'][0]['reviewer'], 'apirev')

    def test_review_creation_requires_purchase(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('api:api_review_create'), {
            'product_slug': self.product.slug, 'rating': 4,
            'title': 'Nope', 'text': 'Never bought it.',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_review_rating_validation(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('api:api_review_create'), {
            'product_slug': self.product.slug, 'rating': 42,
            'title': 'Bad', 'text': 'Bad rating.',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)


class TokenAuthTests(ApiTestBase):
    def test_token_obtain_and_usage(self):
        User.objects.create_user('tokenuser@example.com', 'x1A!aaaa')
        response = self.client.post(reverse('api:api_token'), {
            'username': 'tokenuser@example.com', 'password': 'x1A!aaaa'})
        token = response.data.get('token')
        self.assertTrue(token)
        # Use the token against an authenticated endpoint.
        client = Client()
        response = client.get(reverse('api:api_wishlist'),
                              HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(response.status_code, 200)
