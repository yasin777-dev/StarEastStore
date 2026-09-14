"""Tests for registration, login, profiles and addresses (section 21)."""
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Address, CustomerProfile, User


class UserDataTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_create_user_with_email(self):
        user = User.objects.create_user('ada@example.com', 'Str0ng!Pass99')
        self.assertEqual(user.email, 'ada@example.com')
        self.assertTrue(user.username)  # auto-generated
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password('Str0ng!Pass99'))

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user('', 'pw')

    def test_create_superuser(self):
        user = User.objects.create_superuser('root@example.com', 'Str0ng!Pass99')
        self.assertTrue(user.is_staff and user.is_superuser)

    def test_username_auto_generation_avoids_collisions(self):
        User.objects.create_user('sam@example.com', 'x1A!aaaa')
        user2 = User.objects.create_user('sam@other.com', 'x1A!aaaa')
        self.assertNotEqual(user2.username.lower(), 'sam')

    def test_password_is_hashed_never_plain(self):
        user = User.objects.create_user('hash@example.com', 'Str0ng!Pass99')
        self.assertNotEqual(user.password, 'Str0ng!Pass99')
        self.assertTrue(user.password.startswith(('pbkdf2_', 'argon2', 'bcrypt')))

    def test_profile_auto_created(self):
        user = User.objects.create_user('profile@example.com', 'x1A!aaaa')
        self.assertIsInstance(user.profile, CustomerProfile)


class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.password = 'Str0ng!Pass99'
        self.user = User.objects.create_user(
            'flow@example.com', self.password, first_name='Flow',
        )

    def test_register_creates_user_profile_and_sends_welcome_email(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'new@example.com',
            'first_name': 'New',
            'last_name': 'Customer',
            'phone': '+1 555 010 0000',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        self.assertRedirects(response, reverse('core:home'))
        user = User.objects.get(email='new@example.com')
        self.assertTrue(user.profile)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Welcome', mail.outbox[0].subject)

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'FLOW@example.com',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')

    def test_login_with_email_case_insensitive(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'FLOW@EXAMPLE.COM',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('core:home'))

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'flow@example.com',
            'password': 'wrong-password!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_via_post_only(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('core:home'))
        # GET should not log out (CSRF-safe logout)
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_redirects_to_next(self):
        url = reverse('orders:list')
        response = self.client.post(f'{reverse("accounts:login")}?next={url}', {
            'username': 'flow@example.com',
            'password': self.password,
        })
        self.assertRedirects(response, url)


class ProfileTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('prof@example.com', 'x1A!aaaa')
        self.client.force_login(self.user)

    def test_profile_requires_login(self):
        client = Client()
        response = client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_edit_updates_user_and_profile(self):
        response = self.client.post(reverse('accounts:profile_edit'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'email': 'prof@example.com',
            'phone': '+1 555 999 8888',
            'date_of_birth': '1990-05-01',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.profile.phone, '+1 555 999 8888')

    def test_profile_edit_rejects_taken_email(self):
        User.objects.create_user('taken@example.com', 'x1A!aaaa')
        response = self.client.post(reverse('accounts:profile_edit'), {
            'first_name': 'X', 'last_name': '',
            'email': 'taken@example.com', 'phone': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already used')


class AddressTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('addr@example.com', 'x1A!aaaa')
        self.client.force_login(self.user)
        self.payload = {
            'full_name': 'Addr Tester', 'phone': '5551234567',
            'address_line_1': '1 Main St', 'address_line_2': '',
            'city': 'Springfield', 'state': 'IL', 'postal_code': '62701',
            'country': 'United States', 'is_default': False,
        }

    def test_first_address_becomes_default(self):
        self.client.post(reverse('accounts:address_create'), self.payload)
        address = Address.objects.get(user=self.user)
        self.assertTrue(address.is_default)

    def test_only_one_default(self):
        a1 = Address.objects.create(user=self.user, **self.payload)
        payload2 = {**self.payload, 'is_default': True}
        self.client.post(reverse('accounts:address_create'), payload2)
        a1.refresh_from_db()
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_cannot_see_other_users_addresses(self):
        other = User.objects.create_user('other@example.com', 'x1A!aaaa')
        address = Address.objects.create(user=other, **self.payload)
        response = self.client.get(
            reverse('accounts:address_edit', kwargs={'pk': address.pk}))
        self.assertEqual(response.status_code, 404)

    def test_address_delete(self):
        address = Address.objects.create(user=self.user, **self.payload)
        self.client.post(reverse('accounts:address_delete', kwargs={'pk': address.pk}))
        self.assertFalse(Address.objects.filter(pk=address.pk).exists())


class PasswordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('pw@example.com', 'Old!Pass99')
        self.client.force_login(self.user)

    def test_change_password(self):
        response = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'Old!Pass99',
            'new_password1': 'New!Pass99x',
            'new_password2': 'New!Pass99x',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New!Pass99x'))

    def test_password_reset_flow(self):
        client = Client()
        client.post(reverse('accounts:password_reset'), {'email': 'pw@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].subject.lower())
        # Extract the reset link from the console email body.
        import re

        body = mail.outbox[0].body
        match = re.search(r'/accounts/password-reset/([\w-]+)/([\w-]+)/', body)
        self.assertTrue(match)
        response = client.get(
            reverse('accounts:password_reset_confirm',
                    kwargs={'uidb64': match.group(1), 'token': match.group(2)}),
            follow=True,
        )
        # A valid token redirects to the "set password" step of the same view.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'new password')
        set_password_url = response.wsgi_request.path
        response = client.post(set_password_url,
                               {'new_password1': 'Reset!Pass99',
                                'new_password2': 'Reset!Pass99'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Reset!Pass99'))
