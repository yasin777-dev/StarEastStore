"""Management command to create the default superuser 'yasin'."""

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Creates the default superuser 'yasin' with a preset password."

    def handle(self, *args, **options):
        username = "yasin"
        email = "yasin@stareaststore.com"
        password = "admin123"

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(
                f'Superuser "{username}" already exists — skipping.'
            ))
            return

        user = User.objects.create_superuser(
            email=email,
            password=password,
            username=username,
            first_name="Yasin",
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superuser "{user.username}" created successfully '
            f'(email: {user.email}, is_staff: {user.is_staff}, '
            f'is_superuser: {user.is_superuser})'
        ))
