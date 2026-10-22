"""Make checkout usable on stores set up without the optional demo-data seed."""
from decimal import Decimal

from django.db import migrations


def ensure_default_shipping_method(apps, schema_editor):
    ShippingMethod = apps.get_model('orders', 'ShippingMethod')
    methods = ShippingMethod.objects.using(schema_editor.connection.alias)
    # Never change an existing price or reactivate intentionally disabled methods.
    if not methods.exists():
        methods.create(
            name='Standard shipping',
            price=Decimal('4.99'),
            estimated_delivery='3-5 business days',
            description='Reliable courier delivery',
            sort_order=1,
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [('orders', '0002_alter_order_payment_method')]

    operations = [
        migrations.RunPython(ensure_default_shipping_method, migrations.RunPython.noop),
    ]
