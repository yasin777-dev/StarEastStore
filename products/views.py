"""Catalog views: listing with filters, detail, category/brand/search/sale."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from reviews.models import Review
from reviews.services import user_has_purchased

from .models import Brand, Category, Product, search_products

PAGE_SIZE = 12

SORT_CHOICES = {
    'newest': ('Newest first', '-created_at'),
    'price_asc': ('Price: low to high', 'effective_sort_price'),
    'price_desc': ('Price: high to low', '-effective_sort_price'),
    'popular': ('Most popular', '-total_sales'),
    'name': ('Name: A to Z', 'name'),
}


def _clean_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _filtered_products(request, base_queryset=None):
    """Apply search/filters/sort from GET params; return (queryset, filters)."""
    qs = (base_queryset or Product.objects.listed()).select_related(
        'category', 'brand',
    ).prefetch_related('images')

    params = request.GET
    filters = {}

    query = (params.get('q') or '').strip()
    if query:
        qs = search_products(qs, query)
        filters['q'] = query

    category_slug = params.get('category', '').strip()
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
        filters['category'] = category_slug

    brand_slug = params.get('brand', '').strip()
    if brand_slug:
        qs = qs.filter(brand__slug=brand_slug)
        filters['brand'] = brand_slug

    min_price = _clean_decimal(params.get('min_price'))
    if min_price is not None:
        qs = qs.filter(
            Q(sale_price__isnull=False, sale_price__gte=min_price)
            | Q(sale_price__isnull=True, price__gte=min_price)
        )
        filters['min_price'] = min_price

    max_price = _clean_decimal(params.get('max_price'))
    if max_price is not None:
        qs = qs.filter(
            Q(sale_price__isnull=False, sale_price__lte=max_price)
            | Q(sale_price__isnull=True, price__lte=max_price)
        )
        filters['max_price'] = max_price

    if params.get('in_stock') in {'1', 'true', 'on'}:
        qs = qs.filter(Q(stock_quantity__gt=0) | Q(variants__stock_quantity__gt=0)).distinct()
        filters['in_stock'] = True

    sort = params.get('sort', '')
    if sort == 'price_asc' or sort == 'price_desc':
        # Annotate the price actually charged so sale items sort correctly.
        from django.db.models import (
            Case, DecimalField, ExpressionWrapper, F, When,
        )
        qs = qs.annotate(
            effective_sort_price=ExpressionWrapper(
                Case(
                    When(sale_price__isnull=False, then=F('sale_price')),
                    default=F('price'),
                ),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
        ).order_by(SORT_CHOICES[sort][1])
        filters['sort'] = sort
    elif sort in SORT_CHOICES:
        qs = qs.order_by(SORT_CHOICES[sort][1])
        filters['sort'] = sort

    return qs, filters


def product_list(request):
    """Shop page with pagination, filtering, sorting and search."""
    qs, filters = _filtered_products(request)
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'products/list.html', {
        'page_obj': page,
        'products': page.object_list,
        'filters': filters,
        'categories': Category.objects.filter(is_active=True),
        'brands': Brand.objects.filter(is_active=True),
        'sort_choices': SORT_CHOICES,
        'querystring': _page_querystring(request),
    })


def _page_querystring(request) -> str:
    """Current GET params without the page key (for pagination links)."""
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def product_detail(request, slug: str):
    product = get_object_or_404(
        Product.objects.listed().select_related('category', 'brand')
        .prefetch_related('images', 'variants'),
        slug=slug,
    )
    variants = list(product.variants.filter(is_active=True)) if product.has_variants else []
    related = (
        Product.objects.listed()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related('category', 'brand')
        .prefetch_related('images')[:4]
    )
    reviews = (
        Review.objects.filter(product=product).select_related('user')
    )
    rating_data = product.rating_summary()
    user_review = None
    can_review = False
    if request.user.is_authenticated:
        user_review = reviews.filter(user=request.user).first()
        can_review = user_review is None and user_has_purchased(request.user, product)

    return render(request, 'products/detail.html', {
        'product': product,
        'variants': variants,
        'related_products': related,
        'reviews': reviews[:20],
        'rating_data': rating_data,
        'user_review': user_review,
        'can_review': can_review,
        'review_form': None,  # provided by the reviews app when eligible
    })


def category_detail(request, slug: str):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    qs, filters = _filtered_products(
        request, Product.objects.listed().filter(category=category),
    )
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'products/list.html', {
        'page_obj': page,
        'products': page.object_list,
        'filters': filters,
        'category': category,
        'categories': Category.objects.filter(is_active=True),
        'brands': Brand.objects.filter(is_active=True),
        'sort_choices': SORT_CHOICES,
        'querystring': _page_querystring(request),
    })


def brand_detail(request, slug: str):
    brand = get_object_or_404(Brand, slug=slug, is_active=True)
    qs, filters = _filtered_products(
        request, Product.objects.listed().filter(brand=brand),
    )
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'products/list.html', {
        'page_obj': page,
        'products': page.object_list,
        'filters': filters,
        'brand': brand,
        'categories': Category.objects.filter(is_active=True),
        'brands': Brand.objects.filter(is_active=True),
        'sort_choices': SORT_CHOICES,
        'querystring': _page_querystring(request),
    })


def sale_products(request):
    qs, filters = _filtered_products(request, Product.objects.listed().on_sale())
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'products/list.html', {
        'page_obj': page,
        'products': page.object_list,
        'filters': filters,
        'sale_mode': True,
        'categories': Category.objects.filter(is_active=True),
        'brands': Brand.objects.filter(is_active=True),
        'sort_choices': SORT_CHOICES,
        'querystring': _page_querystring(request),
    })
