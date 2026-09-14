"""Email-based authentication backend (case-insensitive)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailBackend(ModelBackend):
    """Authenticate with either email or username (case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get('email')
        if identifier is None or password is None:
            return None
        try:
            user = User.objects.get(
                Q(email__iexact=identifier) | Q(username__iexact=identifier)
            )
        except User.DoesNotExist:
            User().set_password(password)  # mitigate timing attacks
            return None
        except User.MultipleObjectsReturned:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
