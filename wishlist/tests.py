"""Wishlist tests (section 7)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Category, Product

from .models import WishlistItem

User = get_user_model()


class WishlistTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('wisher@example.com', 'x1A!aaaa')
        self.product = Product.objects.create(
            name='Wish Widget', sku='WW-1',
            category=Category.objects.create(name='Wish Cat'),
            description='Wishable', price=Decimal('12.00'), stock_quantity=5,
        )

    def test_toggle_add_and_remove(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('wishlist:toggle', kwargs={'product_id': self.product.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WishlistItem.objects.filter(
            user=self.user, product=self.product).exists())
        # Toggle again removes it.
        self.client.post(reverse('wishlist:toggle', kwargs={'product_id': self.product.pk}))
        self.assertFalse(WishlistItem.objects.filter(user=self.user).exists())

    def test_duplicate_prevented(self):
        self.client.force_login(self.user)
        for _ in range(3):
            self.client.post(
                reverse('wishlist:toggle', kwargs={'product_id': self.product.pk}))
        self.assertEqual(WishlistItem.objects.filter(user=self.user).count(), 1)

    def test_wishlist_requires_login(self):
        client = Client()
        response = client.get(reverse('wishlist:detail'))
        self.assertEqual(response.status_code, 302)
        response = client.post(
            reverse('wishlist:toggle', kwargs={'product_id': self.product.pk}))
        self.assertEqual(response.status_code, 302)

    def test_move_to_cart(self):
        from cart.services import DatabaseCart

        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('wishlist:move_to_cart', kwargs={'pk': item.pk}))
        self.assertRedirects(response, reverse('cart:detail'))
        self.assertFalse(WishlistItem.objects.filter(pk=item.pk).exists())
        cart = DatabaseCart(self.user)
        self.assertEqual(cart.count(), 1)

    def test_cannot_move_someone_elses_item(self):
        other = User.objects.create_user('otherw@example.com', 'x1A!aaaa')
        item = WishlistItem.objects.create(user=other, product=self.product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('wishlist:move_to_cart', kwargs={'pk': item.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WishlistItem.objects.filter(pk=item.pk).exists())
