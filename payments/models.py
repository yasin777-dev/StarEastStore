"""Payment transaction records (section 10)."""
from __future__ import annotations

import uuid

from django.db import models


class TransactionStatus(models.TextChoices):
    INITIATED = 'initiated', 'Initiated'
    PENDING = 'pending', 'Awaiting gateway'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class PaymentTransaction(models.Model):
    """One payment attempt for an order, with the raw gateway response."""

    reference = models.CharField(max_length=64, unique=True, editable=False)
    transaction_id = models.CharField(
        max_length=255, blank=True,
        help_text='Gateway-side transaction/session identifier.',
    )
    order = models.ForeignKey(
        'orders.Order', on_delete=models.CASCADE, related_name='transactions',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default='USD')
    gateway = models.CharField(max_length=30)
    status = models.CharField(
        max_length=20, choices=TransactionStatus.choices,
        default=TransactionStatus.INITIATED, db_index=True,
    )
    gateway_response = models.JSONField(blank=True, default=dict)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['gateway', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['transaction_id', 'gateway'],
                condition=~models.Q(transaction_id=''),
                name='unique_txn_id_per_gateway',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.gateway}:{self.reference} ({self.status})'

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = uuid.uuid4().hex
        super().save(*args, **kwargs)

    @property
    def is_successful(self) -> bool:
        return self.status == TransactionStatus.SUCCEEDED
