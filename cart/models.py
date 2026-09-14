"""Persisted cart for authenticated users."""
from decimal import Decimal

from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f'Cart of {self.user.email}'

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='cart_items',
    )
    variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.CASCADE,
        related_name='cart_items', blank=True, null=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product', 'variant'],
                name='unique_cart_item_per_product_variant',
            ),
        ]

    def __str__(self) -> str:
        label = self.variant.display_name if self.variant else 'standard'
        return f'{self.quantity} × {self.product.name} ({label})'

    def unit_price(self) -> Decimal:
        if self.variant is not None:
            return self.variant.effective_price
        return self.product.effective_price

    def line_total(self) -> Decimal:
        return self.unit_price() * self.quantity
