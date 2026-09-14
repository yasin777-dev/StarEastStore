from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Accounts'

    def ready(self) -> None:
        # Connect signals (profile auto-creation, cart merge on login).
        from . import signals  # noqa: F401
