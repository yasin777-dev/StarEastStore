"""Import products from a JSON file (default: products/catalog_data/electronics.json).

Usage:  python manage.py import_products [--file PATH]

Idempotent: products are matched by SKU and existing ones are left unchanged.
Each product's ``image`` file is looked up in products/sample_images/.
"""
import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from products.models import Brand, Category, Product, ProductImage

DEFAULT_FILE = Path(settings.BASE_DIR) / 'products' / 'catalog_data' / 'electronics.json'
IMAGE_DIR = Path(settings.BASE_DIR) / 'products' / 'sample_images'


class Command(BaseCommand):
    help = 'Create products (with their images) from a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_FILE), help='Path to the JSON file.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        try:
            items = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'Cannot read {path}: {exc}') from exc

        created = skipped = 0
        for item in items:
            if Product.objects.filter(sku=item['sku']).exists():
                skipped += 1
                self.stdout.write(f'Exists, skipped: {item["sku"]}')
                continue

            category, _ = Category.objects.get_or_create(
                slug=slugify(item['category']), defaults={'name': item['category']},
            )
            brand = None
            if item.get('brand'):
                brand, _ = Brand.objects.get_or_create(
                    slug=slugify(item['brand']), defaults={'name': item['brand']},
                )

            sale = item.get('sale_price')
            product = Product.objects.create(
                name=item['name'],
                slug=item['slug'],
                sku=item['sku'],
                category=category,
                brand=brand,
                short_description=item['short_description'],
                description=item['description'],
                price=Decimal(item['price']),
                sale_price=Decimal(sale) if sale else None,
                stock_quantity=item.get('stock_quantity', 0),
                is_active=True,
            )

            image_path = IMAGE_DIR / item['image']
            if image_path.exists():
                image = ProductImage(product=product, is_primary=True, alt_text=product.name)
                image.image.save(image_path.name, ContentFile(image_path.read_bytes()), save=True)
            else:
                self.stdout.write(self.style.WARNING(f'Missing image file: {image_path}'))

            created += 1
            self.stdout.write(f'Created: {product.name} ({product.sku})')

        self.stdout.write(self.style.SUCCESS(f'Done. Created {created}, skipped {skipped}.'))
