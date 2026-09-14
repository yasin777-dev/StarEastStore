"""Account-related emails (welcome message)."""
from __future__ import annotations

from core.emails import send_templated_email


def send_welcome_email(user) -> bool:
    """Send the welcome email after successful registration."""
    return send_templated_email(
        'emails/welcome_subject.txt',
        'emails/welcome.txt',
        {'user': user},
        user.email,
    )
