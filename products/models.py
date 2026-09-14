"""Catalog models: Category, Brand, Product, ProductImage, ProductVariant."""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify


class ActiveQuerySet(models.QuerySet):
    """Convenience queryset filtering active, purchasable products."""

    def listed(self) -> 'ProductQuerySet':
        return self.filter(is_active=True)


class ProductQuerySet(ActiveQuerySet):
    def featured(self):
        return self.filter(featured=True)

    def on_sale(self):
        return self.filter(sale_price__isnull=False)

    def in_stock(self):
        return self.filter(stock_quantity__gt=0)

    def for_category(self, category):
        return self.filter(category=category)

    def for_brand(self, brand):
        return self.filter(brand=brand)


class SlugModel(models.Model):
    """Shared slug behaviour for category/brand/product."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True, allow_unicode=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_unique_slug()
        super().save(*args, **kwargs)

    def generate_unique_slug(self) -> str:
        base = slugify(self.name)[:160] or 'item'
        slug, index = base, 2
        model = type(self)
        while model.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{index}'
            index += 1
        return slug

    def __str__(self) -> str:
        return self.name


class Category(SlugModel):
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']
        indexes = [models.Index(fields=['slug', 'is_active'])]

    def get_absolute_url(self) -> str:
        return reverse('products:category', kwargs={'slug': self.slug})

    def active_product_count(self) -> int:
        return self.products.filter(is_active=True).count()


class Brand(SlugModel):
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='brands/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['slug', 'is_active'])]

    def get_absolute_url(self) -> str:
        return reverse('products:brand', kwargs={'slug': self.slug})

    def active_product_count(self) -> int:
        return self.products.filter(is_active=True).count()


class Product(SlugModel):
    """The core sellable item. Products may optionally have variants."""

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='products',
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, related_name='products',
        blank=True, null=True,
    )
    sku = models.CharField(max_length=64, unique=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(
        default=5, help_text='Alert when stock falls to or below this level.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    featured = models.BooleanField(default=False)
    total_sales = models.PositiveIntegerField(
        default=0, help_text='Units sold; used for the popularity sort.',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'featured']),
            models.Index(fields=['price']),
            models.Index(fields=['is_active', 'total_sales']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(price__gte=0), name='product_price_non_negative',
            ),
            models.CheckConstraint(
                check=Q(sale_price__isnull=True) | Q(sale_price__lte=models.F('price')),
                name='product_sale_price_lte_price',
            ),
        ]

    def get_absolute_url(self) -> str:
        return reverse('products:detail', kwargs={'slug': self.slug})

    # -- pricing ----------------------------------------------------------
    @property
    def effective_price(self) -> Decimal:
        """The price actually charged: sale price when set (and cheaper)."""
        if self.sale_price is not None and self.sale_price < self.price:
            return self.sale_price
        return self.price

    @property
    def is_on_sale(self) -> bool:
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def discount_percent(self) -> int:
        if not self.is_on_sale or self.price == 0:
            return 0
        return round((1 - self.sale_price / self.price) * 100)

    # -- stock -------------------------------------------------------------
    @property
    def is_in_stock(self) -> bool:
        if self.has_variants:
            return any(v.is_in_stock for v in self.variants.all())
        return self.stock_quantity > 0

    @property
    def stock_status(self) -> str:
        if not self.is_in_stock:
            return 'out_of_stock'
        if self.has_variants:
            return 'in_stock'
        if self.stock_quantity <= self.low_stock_threshold:
            return 'low_stock'
        return 'in_stock'

    @property
    def has_variants(self) -> bool:
        return self.pk and self.variants.filter(is_active=True).exists()

    @property
    def active_variant_list(self) -> list['ProductVariant']:
        if not self.pk:
            return []
        return list(self.variants.filter(is_active=True))

    # -- images ------------------------------------------------------------
    def primary_image(self):
        """Return the primary ProductImage or None (never raises)."""
        images = list(self.images.all()) if self.pk else []
        if not images:
            return None
        for image in images:
            if image.is_primary:
                return image
        return images[0]

    def rating_summary(self) -> dict:
        """Average rating + count, computed from approved reviews."""
        from reviews.models import Review

        return Review.objects.ratings_for_product(self)

    def available_stock_for(self, variant=None) -> int:
        if variant is not None:
            return variant.stock_quantity
        if self.has_variants:
            return sum(v.stock_quantity for v in self.variants.filter(is_active=True))
        return self.stock_quantity

    def apply_variants(self) -> list['ProductVariant']:
        return list(self.variants.filter(is_active=True))


class ProductImage(models.Model):
    """Multiple images per product; one may be flagged as primary."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/%Y/%m/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-is_primary', 'display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=Q(is_primary=True),
                name='unique_primary_image_per_product',
            ),
        ]

    def __str__(self) -> str:
        return f'Image for {self.product.name}'

    def save(self, *args, **kwargs):
        """Keep a single primary image per product."""
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk,
            ).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    """A purchasable variant such as Size/Color with its own SKU and stock."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Optional. Falls back to the product effective price.',
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'size', 'color'],
                condition=~Q(size='') | ~Q(color=''),
                name='unique_variant_per_product_size_color',
            ),
            models.CheckConstraint(
                check=~(Q(size='') & Q(color='')),
                name='variant_has_size_or_color',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.product.name} ({self.display_name})'

    @property
    def display_name(self) -> str:
        return ' / '.join(v for v in (self.size, self.color) if v) or 'Default'

    @property
    def is_in_stock(self) -> bool:
        return self.stock_quantity > 0

    @property
    def effective_price(self) -> Decimal:
        if self.price is not None:
            return self.price
        return self.product.effective_price


class SearchService:
    """Product search (section 16) with PostgreSQL full-text when available."""

    @staticmethod
    def search(queryset, term: str):
        term = (term or '').strip()
        if not term:
            return queryset
        from django.db import connection

        if connection.vendor == 'postgresql':
            return SearchService._postgres_search(queryset, term)
        return SearchService._fallback_search(queryset, term)

    @staticmethod
    def _postgres_search(queryset, term: str):
        from django.contrib.postgres.search import (
            SearchQuery, SearchRank, SearchVector,
        )

        vector = (
            SearchVector('name', weight='A')
            + SearchVector('short_description', 'description', weight='B')
            + SearchVector('sku', weight='A')
            + SearchVector('brand__name', 'category__name', weight='C')
        )
        query = SearchQuery(term)
        return (
            queryset.annotate(search_rank=SearchRank(vector, query))
            .filter(search_rank__gt=0.01)
            .order_by('-search_rank')
        )

    @staticmethod
    def _fallback_search(queryset, term: str):
        from django.db.models import F

        return (
            queryset.annotate(
                search_rank=F('total_sales'),
            ).filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(short_description__icontains=term)
                | Q(sku__icontains=term)
                | Q(brand__name__icontains=term)
                | Q(category__name__icontains=term)
            )
        )


def search_products(queryset, term: str):
    """Public helper wrapping SearchService."""
    return SearchService.search(queryset, term)
