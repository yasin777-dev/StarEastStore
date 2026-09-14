"""Catalog model + view tests: search, filters, sorting, pagination."""
import uuid
from decimal import Decimal

from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Brand, Category, Product, ProductImage, ProductVariant, search_products


def make_product(name='Test Widget', price='50.00', sale_price=None,
                 stock=10, category=None, brand=None, **kwargs):
    defaults = dict(
        sku=kwargs.pop('sku', None) or f"SKU-{uuid.uuid4().hex[:10]}",
        category=category or Category.objects.create(name=f'Cat-{name[:8]}'),
        brand=brand,
        description='A wonderful test widget for testing purposes.',
        short_description='Test widget',
        price=Decimal(price),
        sale_price=Decimal(sale_price) if sale_price else None,
        stock_quantity=stock,
        is_active=True,
    )
    defaults.update(kwargs)
    return Product.objects.create(name=name, **defaults)


class ProductModelTests(TestCase):
    def test_slug_auto_generated_and_unique(self):
        p1 = make_product('Cool Gadget')
        p2 = make_product('Cool Gadget')
        self.assertEqual(p1.slug, 'cool-gadget')
        self.assertNotEqual(p2.slug, p1.slug)

    def test_sku_unique(self):
        make_product('A', sku='DUP-1')
        with self.assertRaises(IntegrityError):
            make_product('B', sku='DUP-1')

    def test_effective_price_and_sale_flag(self):
        product = make_product(price='100.00', sale_price='80.00')
        self.assertEqual(product.effective_price, Decimal('80.00'))
        self.assertTrue(product.is_on_sale)
        self.assertEqual(product.discount_percent, 20)

    def test_sale_price_cannot_exceed_price(self):
        category = Category.objects.create(name='Constraint Cat')
        with self.assertRaises(IntegrityError):
            Product.objects.create(
                name='Bad Pricing', sku='BAD-1', category=category,
                description='x', price=Decimal('10.00'), sale_price=Decimal('11.00'),
            )

    def test_negative_price_rejected(self):
        category = Category.objects.create(name='Neg Cat')
        with self.assertRaises(IntegrityError):
            Product.objects.create(
                name='Negative', sku='NEG-1', category=category,
                description='x', price=Decimal('-1.00'),
            )

    def test_stock_status_low_stock(self):
        product = make_product(stock=3)
        product.low_stock_threshold = 5
        self.assertEqual(product.stock_status, 'low_stock')
        product.stock_quantity = 0
        self.assertEqual(product.stock_status, 'out_of_stock')
        self.assertFalse(product.is_in_stock)

    def test_variant_stock_rolls_up(self):
        product = make_product(stock=0)
        ProductVariant.objects.create(
            product=product, size='M', color='Black',
            sku='VAR-1', stock_quantity=7,
        )
        self.assertTrue(product.is_in_stock)
        self.assertEqual(product.available_stock_for(), 7)

    def test_variant_requires_size_or_color(self):
        product = make_product()
        with self.assertRaises(IntegrityError):
            ProductVariant.objects.create(product=product, sku='VAR-EMPTY')

    def test_primary_image_unique_per_product(self):
        product = make_product()
        ProductImage.objects.create(product=product, image='', is_primary=True)
        ProductImage.objects.create(product=product, image='', is_primary=True)
        self.assertEqual(product.images.filter(is_primary=True).count(), 1)

    def test_inactive_products_not_listed(self):
        product = make_product(is_active=False)
        self.assertNotIn(product, Product.objects.listed())


class CatalogViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_ref = Client()
        cls.cat_electronics = Category.objects.create(name='Electronics')
        cls.cat_books = Category.objects.create(name='Books')
        cls.brand_nova = Brand.objects.create(name='NovaTech')
        cls.brand_aurora = Brand.objects.create(name='Aurora')
        cls.p1 = make_product('Alpha Laptop', price='1000.00', stock=5,
                              category=cls.cat_electronics, brand=cls.brand_nova)
        cls.p2 = make_product('Beta Book', price='20.00', sale_price='15.00',
                              stock=50, category=cls.cat_books, brand=cls.brand_aurora,
                              featured=True)
        cls.p3 = make_product('Gamma Phone', price='500.00', stock=0,
                              category=cls.cat_electronics, brand=cls.brand_nova)
        cls.p_hidden = make_product('Hidden Item', is_active=False)

    def test_shop_lists_active_products_only(self):
        response = self.client_ref.get(reverse('products:list'))
        self.assertContains(response, 'Alpha Laptop')
        self.assertNotContains(response, 'Hidden Item')

    def test_pagination(self):
        for i in range(15):
            make_product(f'Bulk Product {i}', category=self.cat_books)
        response = self.client_ref.get(reverse('products:list'))
        self.assertEqual(len(response.context['products']), 12)  # PAGE_SIZE
        response = self.client_ref.get(reverse('products:list'), {'page': 2})
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_category_filter_page(self):
        response = self.client_ref.get(
            reverse('products:category', kwargs={'slug': self.cat_electronics.slug}))
        self.assertContains(response, 'Alpha Laptop')
        self.assertNotContains(response, 'Beta Book')

    def test_brand_filter_page(self):
        response = self.client_ref.get(
            reverse('products:brand', kwargs={'slug': self.brand_aurora.slug}))
        self.assertContains(response, 'Beta Book')
        self.assertNotContains(response, 'Alpha Laptop')

    def test_sale_page_shows_only_discounted(self):
        response = self.client_ref.get(reverse('products:sale'))
        self.assertContains(response, 'Beta Book')
        self.assertNotContains(response, 'Alpha Laptop')

    def test_search_view(self):
        response = self.client_ref.get(reverse('products:search'), {'q': 'laptop'})
        self.assertContains(response, 'Alpha Laptop')
        self.assertNotContains(response, 'Beta Book')

    def test_search_matches_sku_brand_and_category(self):
        response = self.client_ref.get(
            reverse('products:search'), {'q': self.p1.sku})
        self.assertContains(response, 'Alpha Laptop')
        response = self.client_ref.get(reverse('products:search'), {'q': 'NovaTech'})
        self.assertContains(response, 'Alpha Laptop')
        response = self.client_ref.get(reverse('products:search'), {'q': 'Books'})
        self.assertContains(response, 'Beta Book')

    def test_price_filtering(self):
        response = self.client_ref.get(reverse('products:list'),
                                       {'min_price': '100', 'max_price': '600'})
        self.assertContains(response, 'Gamma Phone')
        self.assertNotContains(response, 'Beta Book')
        # sale price used for filtered products
        response = self.client_ref.get(reverse('products:list'), {'max_price': '16'})
        self.assertContains(response, 'Beta Book')

    def test_availability_filter(self):
        response = self.client_ref.get(reverse('products:list'), {'in_stock': '1'})
        self.assertContains(response, 'Alpha Laptop')
        self.assertNotContains(response, 'Gamma Phone')

    def test_sorting_by_price(self):
        response = self.client_ref.get(reverse('products:list'), {'sort': 'price_asc'})
        products = list(response.context['products'])
        prices = [p.effective_price for p in products]
        self.assertEqual(prices, sorted(prices))

    def test_sorting_newest_first(self):
        response = self.client_ref.get(reverse('products:list'), {'sort': 'newest'})
        products = list(response.context['products'])
        created = [p.created_at for p in products]
        self.assertEqual(created, sorted(created, reverse=True))

    def test_invalid_page_falls_back(self):
        response = self.client_ref.get(reverse('products:list'), {'page': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)

    def test_product_detail(self):
        response = self.client_ref.get(
            reverse('products:detail', kwargs={'slug': self.p1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Laptop')
        self.assertContains(response, self.p1.sku)

    def test_inactive_product_detail_404(self):
        response = self.client_ref.get(
            reverse('products:detail', kwargs={'slug': self.p_hidden.slug}))
        self.assertEqual(response.status_code, 404)

    def test_related_products_same_category(self):
        response = self.client_ref.get(
            reverse('products:detail', kwargs={'slug': self.p1.slug}))
        related = response.context['related_products']
        self.assertIn(self.p3, related)
        self.assertNotIn(self.p1, related)


class SearchServiceTests(TestCase):
    def test_search_empty_term_returns_queryset(self):
        make_product('Anything')
        qs = search_products(Product.objects.listed(), '')
        self.assertEqual(qs.count(), 1)

    def test_search_fallback_sqlite_matches_description(self):
        product = make_product('Mystery Item', )
        product.description = 'A rare zephyrblade for collectors.'
        product.save()
        qs = search_products(Product.objects.listed(), 'zephyrblade')
        self.assertIn(product, qs)
