"""Order, OrderItem and ShippingMethod models (sections 8-9)."""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    PROCESSING = 'processing', 'Processing'
    SHIPPED = 'shipped', 'Shipped'
    DELIVERED = 'delivered', 'Delivered'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'
    COD_PENDING = 'cod_pending', 'Cash on delivery'


class PaymentMethod(models.TextChoices):
    COD = 'cod', 'Cash on delivery'
    SIMULATED = 'simulated', 'Demo gateway'
    STRIPE = 'stripe', 'Stripe'
    RAZORPAY = 'razorpay', 'Razorpay'


def generate_order_number() -> str:
    """Human-friendly unique order number, e.g. ORD-20260914-8FK2QA."""
    stamp = timezone.now().strftime('%Y%m%d')
    return f'ORD-{stamp}-{get_random_string(length=6, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")}'


class ShippingMethod(models.Model):
    """Flat-rate shipping options managed from the admin."""

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    estimated_delivery = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self) -> str:
        return f'{self.name} ({self.price})'


class Order(models.Model):
    """A placed order. Money amounts are snapshots computed on the backend."""

    order_number = models.CharField(max_length=30, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders',
    )
    email = models.EmailField(help_text='Contact email snapshot at order time.')
    # Shipping address snapshot (decoupled from the mutable Address row).
    shipping_full_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=20)
    shipping_address_line_1 = models.CharField(max_length=255)
    shipping_address_line_2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_postal_code = models.CharField(max_length=20)
    shipping_country = models.CharField(max_length=100)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2)

    shipping_method = models.ForeignKey(
        ShippingMethod, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='orders',
    )
    shipping_method_name = models.CharField(max_length=100, blank=True)

    payment_method = models.CharField(
        max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.SIMULATED,
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING,
        db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING,
        db_index=True,
    )
    stock_deducted = models.BooleanField(
        default=False, help_text='Guards against double stock reduction.',
    )
    customer_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', 'payment_status']),
        ]

    def __str__(self) -> str:
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._unique_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _unique_order_number() -> str:
        for _ in range(10):
            candidate = generate_order_number()
            if not Order.objects.filter(order_number=candidate).exists():
                return candidate
        raise RuntimeError('Could not generate a unique order number.')

    # -- helpers -------------------------------------------------------------
    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('orders:detail', kwargs={'order_number': self.order_number})

    @property
    def shipping_address_one_line(self) -> str:
        parts = [
            self.shipping_address_line_1, self.shipping_address_line_2,
            self.shipping_city, self.shipping_state, self.shipping_postal_code,
            self.shipping_country,
        ]
        return ', '.join(p for p in parts if p)

    @property
    def is_paid(self) -> bool:
        return self.payment_status == self.PaymentStatus.PAID

    @property
    def can_be_cancelled_by_customer(self) -> bool:
        return self.status in {
            OrderStatus.PENDING, OrderStatus.CONFIRMED,
        } and self.status != OrderStatus.SHIPPED

    @property
    def status_history(self):
        return self.status_updates.select_related('changed_by').order_by('created_at')

    def current_transaction(self):
        return self.transactions.order_by('-created_at').first()


class OrderItem(models.Model):
    """Snapshot of a purchased line: prices and names are frozen at buy time."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'products.Product', on_delete=models.PROTECT, related_name='order_items',
        blank=True, null=True,
    )
    variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.PROTECT,
        related_name='order_items', blank=True, null=True,
    )
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=120, blank=True)
    sku = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.quantity} × {self.product_name}'

    @classmethod
    def from_cart_line(cls, order: Order, line) -> 'OrderItem':
        """Build a snapshot row from a cart line (prices come from backend)."""
        variant_name = line.variant.display_name if line.variant else ''
        return cls(
            order=order,
            product=line.product,
            variant=line.variant,
            product_name=line.product.name,
            variant_name=variant_name,
            sku=line.variant.sku if line.variant else line.product.sku,
            quantity=line.quantity,
            unit_price=line.unit_price,
            total_price=line.line_total,
        )


class OrderStatusUpdate(models.Model):
    """Audit trail of order status changes (also drives notification emails)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_updates')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'order status updates'

    def __str__(self) -> str:
        return f'{self.order.order_number}: {self.from_status or "—"} → {self.to_status}'
