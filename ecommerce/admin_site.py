"""
A custom AdminSite with an operations dashboard.

Section 13 requires dashboard statistics (total sales, orders, customers,
products, low-stock products, recent orders).  Subclassing ``AdminSite`` lets
us inject that data into the ``admin/index.html`` template.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce

from products.models import Product
from orders.models import Order


class StarEastAdminSite(admin.AdminSite):
    """Admin site with shop statistics rendered on the index page."""

    site_header = 'StarEastStore Administration'
    site_title = 'StarEastStore Admin'
    index_title = 'Store operations dashboard'

    def get_dashboard_stats(self) -> dict:
        """Aggregate the headline numbers shown on the admin home page."""
        sales = Order.objects.filter(payment_status__in=['paid', 'refunded']).aggregate(
            total_sales=Coalesce(Sum('total'), 0, output_field=DecimalField()),
            paid_orders=Count('id'),
        )
        low_stock = list(
            Product.objects.filter(
                is_active=True,
                stock_quantity__lte=F('low_stock_threshold'),
            ).select_related('category')[:12]
        )
        low_stock_count = Product.objects.filter(
            is_active=True, stock_quantity__lte=F('low_stock_threshold'),
        ).count()
        recent_orders = Order.objects.select_related('user')[:10]
        try:
            from reviews.models import Review
            avg_rating = Review.objects.aggregate(avg=Avg('rating'))['avg']
        except Exception:  # pragma: no cover - app not migrated yet
            avg_rating = None
        return {
            'total_sales': sales['total_sales'] or 0,
            'paid_orders': sales['paid_orders'],
            'orders_count': Order.objects.count(),
            'pending_orders': Order.objects.filter(status='pending').count(),
            'customers_count': get_user_model().objects.filter(is_staff=False).count(),
            'products_count': Product.objects.count(),
            'low_stock_products': low_stock,
            'low_stock_count': low_stock_count,
            'recent_orders': recent_orders,
            'avg_rating': avg_rating,
        }

    def each_context(self, request):
        return super().each_context(request)

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self.get_dashboard_stats())
        return super().index(request, extra_context=extra_context)


admin_site = StarEastAdminSite(name='admin')
