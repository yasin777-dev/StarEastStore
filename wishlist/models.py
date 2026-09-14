"""User wishlist (section 7)."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class WishlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items',
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='wishlist_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'], name='unique_wishlist_entry',
            ),
        ]
        indexes = [models.Index(fields=['user', '-created_at'])]

    def __str__(self) -> str:
        return f'{self.user.email} ♥ {self.product.name}'
