"""Account signals: profile auto-creation and guest-cart merge on login."""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in

from cart.services import merge_session_cart_into_user_cart


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_customer_profile(sender, instance, created, **kwargs):
    """Every user gets a CustomerProfile row automatically."""
    if created:
        from .models import CustomerProfile

        CustomerProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def merge_guest_cart(sender, request, user, **kwargs):
    """Fold the guest session cart into the persisted user cart."""
    merge_session_cart_into_user_cart(request, user)
