"""Templated email helpers used across the apps (section 19).

Sending is wrapped defensively: a misconfigured SMTP backend must never break
a checkout. Errors are logged instead of raised.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_templated_email(
    subject_template_name: str,
    email_template_name: str,
    context: dict,
    to_email: str | list[str],
    from_email: str | None = None,
) -> bool:
    """Render subject/body templates and send. Returns True on success."""
    try:
        recipients = [to_email] if isinstance(to_email, str) else list(to_email)
        subject = render_to_string(subject_template_name, context).strip()
        body = render_to_string(email_template_name, context)
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        message.send()
        return True
    except Exception:  # pragma: no cover - depends on SMTP config
        logger.exception('Failed to send email to %s', to_email)
        return False
