"""Remove the discount coupon feature.

Coupon codes are no longer offered at checkout, so the coupon table and the
Order -> Coupon link are dropped. Order.discount is kept on purpose (it simply
stays 0.00 for new orders) so historical money figures remain readable.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_coupon_first_order_only_coupon_per_user_limit'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='coupon',
        ),
        migrations.DeleteModel(
            name='coupon',
        ),
    ]
