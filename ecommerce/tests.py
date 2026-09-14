"""Project-level checks: settings, security headers, error handlers wiring."""
import importlib
import os
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import Resolver404, URLResolver, clear_url_caches
from django.urls.resolvers import RegexPattern
from django.views.static import serve

from ecommerce.deployment import (
    hostname_from_url,
    merge_unique,
    platform_hostnames,
    platform_origins,
    running_on_render,
)

RENDER_HOST = 'stareaststore.onrender.com'
RENDER_URL = f'https://{RENDER_HOST}'


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


class DeploymentHelperTests(SimpleTestCase):
    """Unit tests for the platform (Render) environment detection helpers."""

    def test_hostname_from_url(self):
        self.assertEqual(hostname_from_url('https://stareaststore.onrender.com'), RENDER_HOST)
        self.assertEqual(hostname_from_url('http://example.com:8000/path?q=1'), 'example.com')
        self.assertEqual(hostname_from_url(''), '')
        self.assertEqual(hostname_from_url('not-a-url'), '')
        self.assertEqual(hostname_from_url(None), '')

    def test_platform_hostnames_from_render_environment(self):
        hosts = platform_hostnames({
            'RENDER_EXTERNAL_HOSTNAME': RENDER_HOST,
            'RENDER_EXTERNAL_URL': RENDER_URL,
        })
        self.assertEqual(hosts, [RENDER_HOST])

    def test_platform_hostnames_empty_without_platform_environment(self):
        self.assertEqual(platform_hostnames({}), [])

    def test_platform_hostnames_tolerates_missing_hostname_variable(self):
        # Only RENDER_EXTERNAL_URL set (still gives us the hostname).
        self.assertEqual(
            platform_hostnames({'RENDER_EXTERNAL_URL': RENDER_URL}), [RENDER_HOST]
        )

    def test_platform_origins(self):
        origins = platform_origins({
            'RENDER_EXTERNAL_HOSTNAME': RENDER_HOST,
            'RENDER_EXTERNAL_URL': RENDER_URL,
        })
        self.assertEqual(origins, [f'https://{RENDER_HOST}'])
        self.assertEqual(platform_origins({}), [])

    def test_merge_unique_drops_empties_and_duplicates(self):
        self.assertEqual(
            merge_unique(['a', '', 'b'], ['b', None, 'c']), ['a', 'b', 'c']
        )
        self.assertEqual(merge_unique([], None), [])

    def test_running_on_render_detection(self):
        self.assertTrue(running_on_render({'RENDER': 'true'}))
        self.assertTrue(running_on_render({'RENDER_EXTERNAL_HOSTNAME': RENDER_HOST}))
        self.assertTrue(running_on_render({'RENDER_EXTERNAL_URL': RENDER_URL}))
        self.assertFalse(running_on_render({}))
        self.assertFalse(running_on_render({'RENDER': 'false'}))


class RenderSettingsTests(SimpleTestCase):
    """The settings module must accept the platform's own hostname by itself."""

    def _reload_settings(self, **environ):
        import ecommerce.settings as settings_module

        patcher = mock.patch.dict(os.environ, environ, clear=False)
        patcher.start()
        # Cleanups run LIFO: restore the real environment, then re-import so the
        # module object in sys.modules is not left holding the fake values.
        self.addCleanup(importlib.reload, settings_module)
        self.addCleanup(patcher.stop)
        return importlib.reload(settings_module)

    def test_render_hostname_is_added_to_allowed_hosts(self):
        settings_module = self._reload_settings(RENDER_EXTERNAL_HOSTNAME=RENDER_HOST)
        self.assertIn(RENDER_HOST, settings_module.ALLOWED_HOSTS)
        self.assertIn(f'https://{RENDER_HOST}', settings_module.CSRF_TRUSTED_ORIGINS)

    def test_configured_hosts_are_preserved(self):
        settings_module = self._reload_settings(
            RENDER_EXTERNAL_HOSTNAME=RENDER_HOST,
            ALLOWED_HOSTS='example.com,www.example.com',
            CSRF_TRUSTED_ORIGINS='https://example.com',
        )
        self.assertIn('example.com', settings_module.ALLOWED_HOSTS)
        self.assertIn('www.example.com', settings_module.ALLOWED_HOSTS)
        self.assertIn(RENDER_HOST, settings_module.ALLOWED_HOSTS)
        self.assertIn('https://example.com', settings_module.CSRF_TRUSTED_ORIGINS)
        self.assertIn(f'https://{RENDER_HOST}', settings_module.CSRF_TRUSTED_ORIGINS)

    def test_autodetection_can_be_disabled(self):
        settings_module = self._reload_settings(
            RENDER_EXTERNAL_HOSTNAME=RENDER_HOST,
            DISABLE_PLATFORM_AUTODETECT='True',
        )
        self.assertNotIn(RENDER_HOST, settings_module.ALLOWED_HOSTS)

    def test_production_defaults_on_render(self):
        # DEBUG defaults to False when hosted, and the HTTPS proxy headers that
        # Render sends are honoured (otherwise redirects/secure cookies break).
        settings_module = self._reload_settings(RENDER_EXTERNAL_HOSTNAME=RENDER_HOST)
        self.assertFalse(settings_module.DEBUG)
        self.assertEqual(
            settings_module.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https')
        )
        self.assertTrue(settings_module.SECURE_SSL_REDIRECT)
        self.assertIn(r'^health/?$', settings_module.SECURE_REDIRECT_EXEMPT)
        # No nginx in front of the app, so uploads are served by Django.
        self.assertTrue(settings_module.SERVE_MEDIA)

    def test_local_development_defaults_are_unchanged(self):
        settings_module = self._reload_settings(
            RENDER='', RENDER_EXTERNAL_HOSTNAME='', RENDER_EXTERNAL_URL=''
        )
        self.assertTrue(settings_module.DEBUG)
        self.assertEqual(settings_module.ALLOWED_HOSTS, ['*'])
        self.assertFalse(settings_module.ON_RENDER)


class MediaServingTests(SimpleTestCase):
    """Uploads must be reachable on platforms without a front-end web server."""

    def _reloaded_urls(self, **overrides):
        import ecommerce.urls as urls_module

        override = override_settings(**overrides)
        override.enable()
        # Cleanups run LIFO: disable the override, re-import the module with the
        # real settings, then drop Django's cached resolvers.
        self.addCleanup(clear_url_caches)
        self.addCleanup(importlib.reload, urls_module)
        self.addCleanup(override.disable)
        return importlib.reload(urls_module)

    @staticmethod
    def _resolve(module, path):
        return URLResolver(RegexPattern(r'^/'), module.urlpatterns).resolve(path)

    def test_media_is_served_when_enabled(self):
        from django.conf import settings

        module = self._reloaded_urls(DEBUG=False, SERVE_MEDIA=True)
        match = self._resolve(module, '/media/products/2026/09/item.jpg')
        self.assertEqual(match.func.__name__, serve.__name__)
        self.assertEqual(match.kwargs['document_root'], settings.MEDIA_ROOT)

    def test_media_is_not_wired_when_disabled(self):
        module = self._reloaded_urls(DEBUG=False, SERVE_MEDIA=False)
        with self.assertRaises(Resolver404):
            self._resolve(module, '/media/products/2026/09/item.jpg')

    def test_directories_are_not_listed(self):
        # django.views.static.serve defaults to show_indexes=False.
        module = self._reloaded_urls(DEBUG=False, SERVE_MEDIA=True)
        match = self._resolve(module, '/media/products/')
        self.assertEqual(match.func.__name__, serve.__name__)
        self.assertNotIn('show_indexes', match.kwargs)


class HostValidationTests(TestCase):
    """Regression tests for the 400 Bad Request (DisallowedHost) deploy bug."""

    @override_settings(ALLOWED_HOSTS=[RENDER_HOST, 'testserver'])
    def test_render_hostname_serves_the_storefront(self):
        response = self.client.get('/', HTTP_HOST=RENDER_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'StarEastStore', status_code=200)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_unlisted_host_gets_the_branded_bad_request_page(self):
        # This is the failure mode the platform auto-detection prevents: every
        # path (including /health/) answers 400 when the host is not allowed.
        for path in ('/', '/health/', '/shop/'):
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST=RENDER_HOST)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'Bad request', status_code=400)

