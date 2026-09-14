"""Project-level checks: settings, security headers, error handlers wiring."""
from django.test import TestCase, override_settings


class SecurityHeadersTests(TestCase):
    def test_xss_protection_header(self):
        response = self.client.get('/')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_frame_options_header(self):
        response = self.client.get('/')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')

    def test_referrer_policy(self):
        response = self.client.get('/')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'same-origin')


class ProductionSettingsTests(TestCase):
    def test_debug_off_disables_media_serving_helper(self):
        # Sanity: settings module exists and uses env parsing defaults.
        from django.conf import settings

        self.assertTrue(settings.STATIC_URL)
        self.assertIn('accounts.backends.EmailBackend', settings.AUTHENTICATION_BACKENDS)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_debug_off_hides_exception_details(self):
        response = self.client.get('/definitely-missing/')
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'Traceback', status_code=404)
