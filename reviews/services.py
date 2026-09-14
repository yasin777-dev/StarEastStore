"""Review business rules: verified purchases and submission."""
from __future__ import annotations

from django.db import transaction

from orders.models import Order, OrderStatus

from .models import Review


def user_has_purchased(user, product) -> bool:
    """True when the user has a paid/fulfilled order containing this product."""
    return Order.objects.filter(
        user=user,
        items__product=product,
        status__in=[
            OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
            OrderStatus.SHIPPED, OrderStatus.DELIVERED,
        ],
    ).exclude(status=OrderStatus.CANCELLED).exists()


@transaction.atomic
def submit_review(*, user, product, rating: int, title: str, text: str) -> Review:
    """
    Create or update the user's review of a product. Purchases are enforced:
    only customers who bought the product may review it.
    """
    if not user_has_purchased(user, product):
        raise PermissionError('Only customers who purchased this product can review it.')
    review = Review.objects.filter(product=product, user=user).first()
    if review is None:
        review = Review(product=product, user=user)
    review.rating = int(rating)
    review.title = title.strip()[:150]
    review.text = text.strip()
    review.is_verified_purchase = True
    review.full_clean()  # validates rating bounds, lengths and uniqueness
    review.save()
    return review
