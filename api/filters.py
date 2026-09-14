"""API filtering for the product endpoint."""
import django_filters

from products.models import Product


class ProductFilterSet(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name='category__slug')
    brand = django_filters.CharFilter(field_name='brand__slug')
    min_price = django_filters.NumberFilter(method='filter_min_price')
    max_price = django_filters.NumberFilter(method='filter_max_price')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')

    class Meta:
        model = Product
        fields = ['category', 'brand', 'featured', 'min_price', 'max_price', 'in_stock']

    @staticmethod
    def filter_min_price(queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(sale_price__isnull=False, sale_price__gte=value)
            | Q(sale_price__isnull=True, price__gte=value)
        )

    @staticmethod
    def filter_max_price(queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(sale_price__isnull=False, sale_price__lte=value)
            | Q(sale_price__isnull=True, price__lte=value)
        )

    @staticmethod
    def filter_in_stock(queryset, name, value):
        from django.db.models import Q

        if value:
            return queryset.filter(
                Q(stock_quantity__gt=0) | Q(variants__stock_quantity__gt=0),
            ).distinct()
        return queryset
