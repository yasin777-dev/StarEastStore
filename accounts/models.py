"""Custom user, customer profile and address models (sections 3 & 6)."""
from __future__ import annotations

import re

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

phone_validator = RegexValidator(
    regex=r'^\+?[0-9\s().-]{6,20}$',
    message=_('Enter a valid phone number (6-20 digits, may start with +).'),
)


class UserManager(BaseUserManager):
    """Manager where email is the unique identifier for authentication."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError('An email address must be provided.')
        email = self.normalize_email(email).lower()
        username = extra_fields.pop('username', None) or self.username_for(email)
        extra_fields['username'] = username
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    @classmethod
    def username_for(cls, email: str) -> str:
        """Derive a unique username from the local part of the email."""
        from django.contrib.auth import get_user_model

        local = re.sub(r'[^a-zA-Z0-9_.-]', '', email.split('@')[0]) or 'user'
        candidate, suffix = local, 2
        User = get_user_model()
        while User.objects.filter(username__iexact=candidate).exists():
            candidate = f'{local}{suffix}'
            suffix += 1
        return candidate

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user: registration and login happen with the email address."""

    email = models.EmailField(_('email address'), unique=True, db_index=True)
    username = models.CharField(_('username'), max_length=150, unique=True)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    phone = models.CharField(
        _('phone'), max_length=20, blank=True, validators=[phone_validator],
    )
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [models.Index(fields=['email', 'is_active'])]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        full = f'{self.first_name} {self.last_name}'.strip()
        return full or self.get_short_name()

    def get_short_name(self) -> str:
        return self.first_name or self.username


class CustomerProfile(models.Model):
    """Extra customer information, auto-created for every user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile',
    )
    image = models.ImageField(
        upload_to='profiles/%Y/%m/', blank=True, null=True,
        help_text=_('Square images look best. Max 5 MB, JPEG/PNG/WebP.'),
    )
    phone = models.CharField(
        max_length=20, blank=True, validators=[phone_validator],
    )
    date_of_birth = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('customer profile')
        verbose_name_plural = _('customer profiles')

    def __str__(self) -> str:
        return f'Profile of {self.user.email}'


class Address(models.Model):
    """A shipping address. Users can store several; one is the default."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='addresses',
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='United States')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('address')
        verbose_name_plural = _('addresses')
        ordering = ['-is_default', '-updated_at']
        indexes = [models.Index(fields=['user', 'is_default'])]

    def __str__(self) -> str:
        return f'{self.full_name}, {self.address_line_1}, {self.city}'

    def save(self, *args, **kwargs):
        """Keep exactly one default address per user."""
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk,
            ).update(is_default=False)
        elif not Address.objects.filter(user=self.user, is_default=True).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    def one_line(self) -> str:
        parts = [
            self.address_line_1, self.address_line_2, self.city,
            self.state, self.postal_code, self.country,
        ]
        return ', '.join(p for p in parts if p)
