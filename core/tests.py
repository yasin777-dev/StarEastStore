"""Core pages, contact form, error pages, rate limiting, admin dashboard."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from products.models import Category, Product

from .models import ContactMessage

User = get_user_model()


class StaticPageTests(TestCase):
    def test_home_page(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'StarEastStore')

    def test_about_terms_privacy(self):
        for name in ['about', 'terms', 'privacy']:
            response = self.client.get(reverse(f'core:{name}'))
            self.assertEqual(response.status_code, 200)

    def test_home_shows_featured_sections(self):
        category = Category.objects.create(name='Home Cat')
        Product.objects.create(
            name='Featured Item', sku='FH-1', category=category,
            description='Featured', price=Decimal('10.00'), stock_quantity=5,
            featured=True,
        )
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'Featured Item')


class ContactTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_contact_form_saves_and_notifies(self):
        response = self.client.post(reverse('core:contact'), {
            'name': 'Curious', 'email': 'curious@example.com',
            'subject': 'Question', 'message': 'Do you ship internationally?',
            'website': '',
        })
        self.assertRedirects(response, reverse('core:contact_success'))
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_honeypot_blocks_bots(self):
        response = self.client.post(reverse('core:contact'), {
            'name': 'Bot', 'email': 'bot@spam.com', 'subject': 'Spam',
            'message': 'Buy my stuff please, it is great stuff.',
            'website': 'http://spam.example',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_contact_validates_short_message(self):
        response = self.client.post(reverse('core:contact'), {
            'name': 'Hasty', 'email': 'h@example.com',
            'subject': 'Hi', 'message': 'short', 'website': '',
        })
        self.assertEqual(response.status_code, 400)


class ErrorPageTests(TestCase):
    def test_404_branded(self):
        response = self.client.get('/definitely-not-a-page/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page not found', status_code=404)

    def test_403_branded(self):
        from core.views import forbidden

        response = self.client.get('/dummy/')  # 403 raised via handler below
        # Directly test the handler output through the url handler mapping.
        from django.test import RequestFactory

        request = RequestFactory().get('/')
        response = forbidden(request)
        self.assertEqual(response.status_code, 403)


@override_settings(RATELIMIT_ENABLE=True)
class RateLimitTests(TestCase):
    def test_login_rate_limited(self):
        cache.clear()
        client = Client()
        for _ in range(8):
            response = client.post(reverse('accounts:login'), {
                'username': 'nobody@example.com', 'password': 'wrong!Pass1'})
        response = client.post(reverse('accounts:login'), {
            'username': 'nobody@example.com', 'password': 'wrong!Pass1'})
        self.assertEqual(response.status_code, 429)


class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'dash@example.com', 'x1A!aaaa')
        self.client.force_login(self.admin)

    def test_dashboard_stats_render(self):
        category = Category.objects.create(name='Dash Cat')
        Product.objects.create(
            name='Lowstock Widget', sku='LS-1', category=category,
            description='Low', price=Decimal('9.99'), stock_quantity=2,
            low_stock_threshold=5,
        )
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total sales')
        self.assertContains(response, 'Lowstock Widget')
        self.assertContains(response, 'Recent orders')

    def test_admin_requires_staff(self):
        client = Client()
        User.objects.create_user('plain@example.com', 'x1A!aaaa')
        client.force_login(User.objects.get(email='plain@example.com'))
        response = client.get('/admin/')
        self.assertNotEqual(response.status_code, 200)
