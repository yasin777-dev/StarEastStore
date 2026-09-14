"""Product review model (section 12)."""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ReviewQuerySet(models.QuerySet):
    def for_product(self, product):
        return self.filter(product=product).select_related('user')

    def ratings_for_product(self, product) -> dict:
        """Average, count and 1-5 distribution for a product."""
        agg = self.for_product(product).aggregate(
            average=models.Avg('rating'), count=models.Count('id'),
        )
        distribution = {stars: 0 for stars in range(1, 6)}
        counts = (
            self.for_product(product)
            .values_list('rating', flat=True)
        )
        for rating in counts:
            distribution[int(rating)] += 1
        average = agg['average']
        return {
            'average': round(average, 1) if average is not None else None,
            'average_raw': Decimal(str(average)) if average is not None else None,
            'count': agg['count'],
            'distribution': distribution,
        }


class Review(models.Model):
    """One review per (user, product); editing updates the same row."""

    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='reviews',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(max_length=150)
    text = models.TextField()
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'user'], name='unique_review_per_user_product',
            ),
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name='review_rating_between_1_and_5',
            ),
        ]
        indexes = [models.Index(fields=['product', '-created_at'])]

    def __str__(self) -> str:
        return f'{self.rating}★ {self.title} by {self.user.email}'

    @property
    def reviewer_name(self) -> str:
        return self.user.get_full_name() or self.user.username
