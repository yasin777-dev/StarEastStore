"""Review tests: verified-purchase rule, duplicates, ratings (section 12)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from orders.models import Order, OrderItem, OrderStatus, ShippingMethod
from products.models import Category, Product

from .models import Review
from .services import submit_review

User = get_user_model()


class ReviewServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('reviewer@example.com', 'x1A!aaaa')
        self.other = User.objects.create_user('other@example.com', 'x1A!aaaa')
        self.product = Product.objects.create(
            name='Review Target', sku='RT-1',
            category=Category.objects.create(name='Review Cat'),
            description='Reviewable', price=Decimal('15.00'), stock_quantity=5,
        )
        shipping = ShippingMethod.objects.create(name='Std', price=Decimal('2.00'))
        self.order = Order.objects.create(
            user=self.user, email=self.user.email,
            shipping_full_name='R', shipping_phone='555',
            shipping_address_line_1='x', shipping_city='Town',
            shipping_state='TS', shipping_postal_code='1', shipping_country='USA',
            subtotal=Decimal('15.00'), shipping_fee=Decimal('2.00'),
            total=Decimal('17.00'), shipping_method=shipping,
            payment_method='cod', payment_status='cod_pending',
            status=OrderStatus.CONFIRMED,
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            sku=self.product.sku, quantity=1, unit_price=self.product.price,
            total_price=self.product.price,
        )

    def test_purchaser_can_review(self):
        review = submit_review(user=self.user, product=self.product,
                               rating=5, title='Great', text='Loved it.')
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.is_verified_purchase)

    def test_non_purchaser_cannot_review(self):
        with self.assertRaises(PermissionError):
            submit_review(user=self.other, product=self.product,
                          rating=4, title='Nope', text='Never bought this.')

    def test_duplicate_review_updates_same_row(self):
        submit_review(user=self.user, product=self.product,
                      rating=3, title='First', text='First take.')
        submit_review(user=self.user, product=self.product,
                      rating=5, title='Edited', text='Even better after a week.')
        self.assertEqual(Review.objects.filter(product=self.product).count(), 1)
        review = Review.objects.get(product=self.product)
        self.assertEqual(review.title, 'Edited')

    def test_invalid_rating_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            submit_review(user=self.user, product=self.product,
                          rating=9, title='Bad', text='Out of range.')

    def test_cancelled_order_still_counts_as_purchased(self):
        """Buyer with a cancelled order should not be able to review."""
        self.order.status = OrderStatus.CANCELLED
        self.order.save()
        with self.assertRaises(PermissionError):
            submit_review(user=self.user, product=self.product,
                          rating=5, title='x', text='y')


class ReviewViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('viewrev@example.com', 'x1A!aaaa')
        self.product = Product.objects.create(
            name='View Review', sku='VR-1',
            category=Category.objects.create(name='VR Cat'),
            description='Reviewable view', price=Decimal('15.00'), stock_quantity=5,
        )

    def test_review_form_requires_login(self):
        response = self.client.post(
            reverse('reviews:add', kwargs={'product_slug': self.product.slug}),
            {'rating': 5, 'title': 't', 'text': 'text'})
        self.assertEqual(response.status_code, 302)

    def test_rating_distribution_and_average(self):
        Review.objects.create(product=self.product, user=self.user,
                              rating=5, title='a', text='a')
        other = User.objects.create_user('r2@example.com', 'x1A!aaaa')
        Review.objects.create(product=self.product, user=other,
                              rating=4, title='b', text='b')
        data = self.product.rating_summary()
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['average'], 4.5)
        self.assertEqual(data['distribution'][5], 1)
        self.assertEqual(data['distribution'][4], 1)
