"""Safe, repeatable catalog setup; never creates users or changes existing stock."""
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image

from products.models import Brand, Category, Product, ProductImage


class Command(BaseCommand):
    help = 'Add three sample electronics with illustrations and repair missing electronics images.'

    def add_arguments(self, parser):
        parser.add_argument('--repair-only', action='store_true', help='Do not add sample products.')

    def handle(self, *args, **options):
        if not options['repair_only']:
            category, _ = Category.objects.get_or_create(slug='electronics', defaults={'name': 'Electronics'})
            brand, _ = Brand.objects.get_or_create(slug='stellar', defaults={'name': 'Stellar'})
            for sku, name, price in [
                ('SAMPLE-LAPTOP', 'Sample Laptop', '949.00'),
                ('SAMPLE-TV', 'Sample TV', '499.00'),
                ('SAMPLE-HEADPHONES', 'Sample Headphones', '79.00'),
            ]:
                Product.objects.get_or_create(sku=sku, defaults={
                    'name': name, 'category': category, 'brand': brand, 'price': price,
                    'stock_quantity': 10, 'description': 'Demonstration product, shown with a sample illustration.',
                    'short_description': 'Sample catalog item — illustrative image.',
                })
        assets = Path(__file__).resolve().parents[3] / 'products' / 'sample_images'
        repaired = preserved = 0
        for product in Product.objects.prefetch_related('images').iterator(chunk_size=100):
            usable = False
            for photo in product.images.all():
                if not photo.image:
                    continue
                try:
                    with photo.image.open('rb') as file:
                        Image.open(file).verify()
                    # Persist readable legacy uploads before the next redeploy.
                    if not photo.image.name.startswith('catalog/'):
                        with photo.image.open('rb') as file:
                            data = file.read()
                        photo.image.save(Path(photo.image.name).name, ContentFile(data), save=True)
                        preserved += 1
                    usable = True
                except (OSError, ValueError):
                    continue
            if usable:
                continue
            name = product.name.lower()
            kind = next((kind for kind in ('laptop', 'headphones', 'tv') if kind in name), None)
            if kind is None:
                self.stdout.write(f'No usable image: {product.name}; upload a photo in admin.')
                continue
            photo = ProductImage(product=product, is_primary=True,
                                 alt_text=f'{product.name} — sample illustration')
            photo.image.save(f'{kind}.jpg', ContentFile((assets / f'{kind}.jpg').read_bytes()), save=True)
            repaired += 1
        self.stdout.write(self.style.SUCCESS(f'Repaired {repaired} images; preserved {preserved} legacy uploads.'))
