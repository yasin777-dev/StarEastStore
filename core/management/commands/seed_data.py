"""
Seed the store with realistic demo data.

Usage:  python manage.py seed_data
Pass --force to add data on top of an existing database (default behaviour is
to skip if data already exists). Credentials come from the environment with
documented development defaults - never commit real credentials.
"""
import io
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import User
from orders.models import Coupon, ShippingMethod
from products.models import Brand, Category, Product, ProductImage, ProductVariant

# Deterministic-ish but varied palette for generated imagery.
PALETTES = [
    ((79, 70, 229), (147, 197, 253)),
    ((220, 38, 38), (252, 211, 77)),
    ((5, 150, 105), (167, 243, 208)),
    ((124, 58, 237), (251, 207, 232)),
    ((217, 119, 6), (254, 215, 170)),
    ((2, 132, 199), (186, 230, 253)),
    ((190, 24, 93), (253, 186, 116)),
    ((13, 148, 136), (204, 251, 241)),
    ((71, 85, 105), (203, 213, 225)),
    ((101, 163, 13), (217, 249, 157)),
]

ICONS = {
    'Electronics': '💻', 'Fashion': '👕', 'Home & Kitchen': '🍳',
    'Beauty': '💄', 'Sports': '🏀', 'Books': '📚', 'Toys': '🧸',
    'Accessories': '🎒',
}

# Product photos checked into the repo, named after the product SKU
# (e.g. fixtures/product_images/SE-ELEC-001.jpg). Used when present; the
# gradient tile below is only a fallback.
FIXTURE_IMAGE_DIR = os.path.join(settings.BASE_DIR, 'fixtures', 'product_images')


def load_fixture_image(sku: str) -> ContentFile | None:
    """Return the bundled photo for ``sku`` as a ContentFile, or None."""
    for extension in ('jpg', 'jpeg', 'png', 'webp'):
        path = os.path.join(FIXTURE_IMAGE_DIR, f'{sku}.{extension}')
        if os.path.exists(path):
            with open(path, 'rb') as handle:
                return ContentFile(handle.read(), name=f'{sku}.{extension}')
    return None


def render_product_image(product_name: str, category: str, index: int, size: int = 900) -> ContentFile:
    """Render a clean gradient tile with the product emoji/initials."""
    top, bottom = PALETTES[index % len(PALETTES)]
    image = Image.new('RGB', (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / size
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color)

    # Decorative rings
    for radius in range(140, 420, 70):
        draw.ellipse(
            [size // 2 - radius, size // 2 - radius, size // 2 + radius, size // 2 + radius],
            outline=(255, 255, 255), width=3,
        )

    icon = product_name[:2].upper()
    try:
        draw.text((size / 2, size / 2 - 80), icon, anchor='mm', font_size=170,
                  fill='white')
        draw.text((size / 2, size / 2 + 150), product_name[:26], anchor='mm',
                  fill='white', font_size=44)
    except (TypeError, OSError):
        # Very old Pillow without font_size support
        draw.text((size / 2 - 40, size / 2 - 40), icon, fill='white')

    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=88)
    buffer.seek(0)
    return ContentFile(buffer.read(), name='dummy.jpg')


class Command(BaseCommand):
    help = 'Populate the database with demo catalog, users, coupons and orders.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Seed even if data already exists.')

    # ------------------------------------------------------------------ data
    CATEGORIES = [
        ('Electronics', 'Phones, laptops, audio and smart gadgets.'),
        ('Fashion', 'Clothing and footwear for every season.'),
        ('Home & Kitchen', 'Everything to cook, clean and decorate.'),
        ('Beauty', 'Skincare, haircare and self-care essentials.'),
        ('Sports', 'Gear and apparel for training and outdoors.'),
        ('Books', 'Bestsellers, classics and new releases.'),
        ('Toys', 'Playful picks for kids of every age.'),
        ('Accessories', 'Bags, watches and everyday carry.'),
    ]

    BRANDS = ['NovaTech', 'Aurora', 'UrbanEdge', 'PureGlow', 'SummitPro', 'LumiHome']

    # (name, short description, price, sale price or None)
    # SKUs are derived from the category and position, so keep the order stable.
    PRODUCTS = {
        'Electronics': [
            ('Stellar Slim 13 Laptop',
             'Featherlight 13-inch laptop with a vivid OLED display and 18-hour battery.',
             '1099.00', '949.00'),
            ('EchoBuds ANC',
             'True-wireless earbuds with hybrid noise cancellation and a 30-hour charging case.',
             '149.00', None),
            ('ZapCube 100W GaN Charger',
             'Travel-sized 3-port GaN charger that powers laptop, tablet and phone at once.',
             '59.99', '49.99'),
            ('ClearView 27 UHD Display',
             '27-inch 4K IPS display with 65W USB-C power delivery and slim bezels.',
             '429.00', None),
        ],
        'Fashion': [
            ('Aurora Cloud Fleece Hoodie',
             'Brushed-fleece hoodie with a boxy fit and kangaroo pocket.',
             '64.99', None),
            ('UrbanEdge Flex Tapered Trousers',
             'Four-way stretch trousers with a tapered leg for work or weekend.',
             '74.99', '59.99'),
            ('SummitPro AeroLite Training Tee',
             'Ultra-light performance tee with mesh ventilation panels.',
             '34.99', None),
            ('PureGlow Linen Wrap Dress',
             'Breathable linen wrap dress with a flattering tie waist.',
             '89.99', None),
        ],
        'Home & Kitchen': [
            ('LumiHome Halo Ambient Lamp',
             'App-controlled ambient lamp with tunable white and 16 million colours.',
             '79.99', '64.99'),
            ('ForgeLine Chef Knife Trio',
             '3-piece forged knife set: chef, santoku and paring, with walnut handles.',
             '119.00', None),
            ('Daybreak Coffee Dripper Set',
             'Ceramic dripper, glass server and 40 filters for slow-brew mornings.',
             '44.99', None),
            ('Dune Textured Stoneware Vase',
             'Hand-thrown stoneware vase with a matte sand glaze, 28 cm.',
             '39.99', None),
        ],
        'Beauty': [
            ('PureGlow Radiance Booster Serum',
             'Lightweight 20% vitamin C and ferulic acid serum for a brighter complexion.',
             '42.00', None),
            ('Aurora Velvet Lip Colour',
             'Weightless velvet-matte lipstick in shade 12 Terracotta.',
             '24.00', '19.00'),
            ('KeraNourish Deep Repair Mask',
             'Keratin-infused weekly mask for damaged, colour-treated hair.',
             '28.50', None),
            ('DewDrop Barrier Cream',
             'Ceramide-rich daily moisturiser for sensitive skin, 50ml.',
             '32.00', None),
        ],
        'Sports': [
            ('SummitPro Ridge 25L Daypack',
             'Ventilated-back 25L daypack with hydration sleeve and rain cover.',
             '89.00', '74.00'),
            ('GripCore Pro Yoga Mat',
             '5mm cork-topped mat with a natural rubber base and carry strap.',
             '54.99', None),
            ('SwiftSpin Speed Rope',
             'Weighted-handle speed rope with dual ball bearings.',
             '19.99', None),
            ('ApexLift Adjustable Dumbbells',
             'Dial-select 2.5-24kg adjustable dumbbell pair with stand.',
             '299.00', None),
        ],
        'Books': [
            ('Beneath the Amber Tide',
             'A historical mystery set in a 19th-century Baltic port.',
             '18.99', None),
            ('The Focus Protocol',
             'A science-backed system for reclaiming attention in a distracted world.',
             '22.99', '17.99'),
            ('Hearth & Harvest: Seasonal Cooking',
             '100 seasonal recipes from a working farmhouse kitchen.',
             '34.99', None),
            ('Voidfarer: The Last Beacon',
             'First volume in an epic space-opera trilogy.',
             '16.99', None),
        ],
        'Toys': [
            ('BrickQuest Lunar Base Kit',
             '520-piece lunar base construction set with two astronaut figures, ages 7+.',
             '69.99', None),
            ('SnuggleNest Sloth Plush',
             'Super-soft weighted plush sloth, 45cm, machine washable.',
             '29.99', '24.99'),
            ('ThunderDrift RC Buggy',
             '1:16 scale off-road RC buggy with a 25 km/h top speed.',
             '79.99', None),
            ('CosmoSphere Globe Puzzle',
             '3D planet-earth puzzle with an LED stand, 540 pieces.',
             '39.99', None),
        ],
        'Accessories': [
            ('UrbanEdge Voyager Duffel',
             'Waxed-canvas 40L duffel with leather trim and a shoe compartment.',
             '129.00', None),
            ('NovaTime Meridian Watch',
             'Ultra-thin automatic watch with sapphire crystal and a steel mesh strap.',
             '249.00', '209.00'),
            ('Aurora Slimfold Card Wallet',
             'Vegetable-tanned leather cardholder with an RFID shield.',
             '45.00', None),
            ('HorizonShade Polarized Aviators',
             'Lightweight titanium aviators with polarized UV400 lenses.',
             '89.99', None),
        ],
    }

    VARIANT_SPECS = {
        'Fashion': [('S', 'Black'), ('M', 'Black'), ('L', 'Black'), ('M', 'Sand'), ('L', 'Sand')],
        'Sports': [('One Size', 'Gray')],
        'Beauty': [('50ml', '')],
        'Books': [('Hardcover', ''), ('Paperback', '')],
    }

    def handle(self, *args, **options):
        force = options['force']
        if Product.objects.exists() and not force:
            self.stdout.write(self.style.WARNING(
                'Data already exists. Use --force to seed anyway.'))
            return

        random.seed(20260914)
        with transaction.atomic():
            admin, customer = self.create_users()
            categories = self.create_categories()
            brands = self.create_brands()
            products = self.create_products(categories, brands)
            self.create_shipping_methods()
            self.create_coupons()
            self.create_reviews(customer, products)
            self.create_sample_orders(customer, products, admin)

        self.stdout.write(self.style.SUCCESS('\n✅ Seed data created:'))
        self.stdout.write(f'   Admin:      {admin.email} (password from env or "admin12345!")')
        self.stdout.write(f'   Customer:   {customer.email} (password from env or "demo12345!")')
        self.stdout.write(f'   Categories: {len(categories)}  Brands: {len(brands)}  Products: {len(products)}')
        self.stdout.write('   Coupons:    WELCOME10, SAVE5, VIP20')
        self.stdout.write('   Run the server with: python manage.py runserver')

    # ------------------------------------------------------------- creators
    def create_users(self):
        admin_email = os.environ.get('DJANGO_ADMIN_EMAIL', 'admin@stareaststore.com')
        admin_password = os.environ.get('DJANGO_ADMIN_PASSWORD') or 'admin12345!'
        customer_email = os.environ.get('DEMO_CUSTOMER_EMAIL', 'demo@stareaststore.com')
        customer_password = os.environ.get('DEMO_CUSTOMER_PASSWORD') or 'demo12345!'

        if User.objects.filter(email=admin_email).exists():
            admin = User.objects.get(email=admin_email)
        else:
            admin = User.objects.create_superuser(
                email=admin_email, password=admin_password,
                first_name='Store', last_name='Admin', username='storeadmin',
            )
        if User.objects.filter(email=customer_email).exists():
            customer = User.objects.get(email=customer_email)
        else:
            customer = User.objects.create_user(
                email=customer_email, password=customer_password,
                first_name='Demo', last_name='Customer', phone='+1 555 010 7777',
            )
            from accounts.models import Address

            Address.objects.create(
                user=customer, full_name='Demo Customer', phone='+1 555 010 7777',
                address_line_1='42 Harbour Lane', address_line_2='Suite 7',
                city='Portside', state='CA', postal_code='94000',
                country='United States', is_default=True,
            )
        # Extra reviewers for a natural review section.
        for index in range(1, 5):
            email = f'reviewer{index}@stareaststore.com'
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(
                    email=email, password='reviewer12345!',
                    first_name=f'Reviewer {index}', last_name='Seed',
                )
        return admin, customer

    def create_categories(self):
        categories = []
        for name, description in self.CATEGORIES:
            category, created = Category.objects.get_or_create(
                name=name,
                defaults={'description': description, 'is_active': True},
            )
            if created or not category.image:
                content = render_product_image(name, name, len(categories))
                category.image.save(f'{category.slug}.jpg', content, save=True)
            categories.append(category)
        return categories

    def create_brands(self):
        brands = []
        for name in self.BRANDS:
            brand, _created = Brand.objects.get_or_create(
                name=name, defaults={'description': f'{name} - quality you can trust.'},
            )
            brands.append(brand)
        return brands

    def create_products(self, categories, brands):
        products = []
        counter = 0
        for category in categories:
            names = self.PRODUCTS.get(category.name, [])
            for position, (name, short_description, price, sale_price) in enumerate(names):
                counter += 1
                sku = f'SE-{category.slug.upper()[:4]}-{position + 1:03d}'
                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        'name': name,
                        'category': category,
                        'brand': random.choice(brands),
                        'description': (
                            f'{short_description}\n\nThe {name} from our {category.name} '
                            'collection is built to last and designed to delight. '
                            'Quality checked by our team and backed by a 30-day '
                            'return policy.'
                        ),
                        'short_description': short_description,
                        'price': Decimal(price),
                        'sale_price': Decimal(sale_price) if sale_price else None,
                        'stock_quantity': random.choice([0, 3, 8, 25, 40, 60, 120]),
                        'low_stock_threshold': 5,
                        'is_active': True,
                        'featured': position == 0,
                        'total_sales': random.randint(0, 300),
                    },
                )
                if created:
                    photo = load_fixture_image(sku)
                    if photo is not None:
                        # Real product photo shipped with the repo (fixtures/product_images).
                        ProductImage.objects.create(
                            product=product,
                            image=ContentFile(photo.read(), name=f'{product.slug}.jpg'),
                            alt_text=name, is_primary=True, display_order=0,
                        )
                    extra_images = 0 if photo is not None else random.choice([1, 2, 3])
                    for image_index in range(extra_images):
                        content = render_product_image(name, category.name, counter + image_index)
                        ProductImage.objects.create(
                            product=product,
                            image=ContentFile(content.read(),
                                              name=f'{product.slug}-{image_index}.jpg'),
                            alt_text=f'{name} - photo {image_index + 1}',
                            is_primary=image_index == 0,
                            display_order=image_index,
                        )
                    for size, color in self.VARIANT_SPECS.get(category.name, []):
                        ProductVariant.objects.get_or_create(
                            product=product, size=size, color=color,
                            defaults={
                                'sku': f'{product.sku}-{size[:2].upper()}{color[:2].upper()}',
                                'price': None,
                                'stock_quantity': random.choice([0, 4, 12, 30]),
                            },
                        )
                products.append(product)
        return products

    def create_shipping_methods(self):
        ShippingMethod.objects.get_or_create(
            name='Standard shipping',
            defaults={'price': 4.99, 'estimated_delivery': '3-5 business days',
                      'description': 'Reliable courier delivery', 'sort_order': 1},
        )
        ShippingMethod.objects.get_or_create(
            name='Express shipping',
            defaults={'price': 12.99, 'estimated_delivery': '1-2 business days',
                      'description': 'Priority handling', 'sort_order': 2},
        )
        ShippingMethod.objects.get_or_create(
            name='Pickup point',
            defaults={'price': 2.49, 'estimated_delivery': '2-4 business days',
                      'description': 'Collect from a nearby locker', 'sort_order': 3},
        )

    def create_coupons(self):
        now = timezone.now()
        Coupon.objects.get_or_create(code='WELCOME10', defaults={
            'discount_type': Coupon.DiscountType.PERCENTAGE, 'discount_value': 10,
            'minimum_order_amount': 20, 'maximum_discount': 20,
            'valid_from': now - timedelta(days=30),
            'valid_until': now + timedelta(days=365), 'is_active': True,
        })
        Coupon.objects.get_or_create(code='SAVE5', defaults={
            'discount_type': Coupon.DiscountType.FIXED, 'discount_value': 5,
            'minimum_order_amount': 30, 'valid_from': now - timedelta(days=10),
            'valid_until': now + timedelta(days=90), 'is_active': True,
        })
        Coupon.objects.get_or_create(code='VIP20', defaults={
            'discount_type': Coupon.DiscountType.PERCENTAGE, 'discount_value': 20,
            'minimum_order_amount': 100, 'maximum_discount': 50, 'usage_limit': 50,
            'valid_from': now - timedelta(days=5),
            'valid_until': now + timedelta(days=45), 'is_active': True,
        })

    def create_reviews(self, customer, products):
        from reviews.models import Review

        snippets = [
            (5, 'Exceeded expectations', 'Great quality for the price. Shipping was quick and the packaging was solid.'),
            (4, 'Very happy', 'Does exactly what it says. Would buy again from this shop.'),
            (5, 'Excellent value', 'Honestly surprised by the quality. Recommended.'),
            (4, 'Good, minor quibbles', 'Solid product overall; wished it came in more colors.'),
        ]
        users = list(User.objects.filter(email__startswith='reviewer'))
        users.append(customer)
        reviewed = random.sample(products, k=min(14, len(products)))
        for product in reviewed:
            user = random.choice(users)
            rating, title, text = random.choice(snippets)
            Review.objects.get_or_create(
                product=product, user=user,
                defaults={'rating': rating, 'title': title, 'text': text,
                          'is_verified_purchase': True},
            )

    def create_sample_orders(self, customer, products, admin):
        from orders.models import Order, OrderItem, OrderStatus, OrderStatusUpdate

        if Order.objects.exists():
            return
        for days_ago, final_status in [(12, OrderStatus.DELIVERED),
                                       (3, OrderStatus.SHIPPED)]:
            picked = random.sample(products, k=3)
            subtotal = sum(p.effective_price for p in picked)
            shipping_fee = Decimal('4.99')
            tax = (subtotal * settings.TAX_RATE).quantize(Decimal('0.01'))
            total = subtotal + shipping_fee + tax
            order = Order.objects.create(
                user=customer, email=customer.email,
                shipping_full_name='Demo Customer', shipping_phone='+1 555 010 7777',
                shipping_address_line_1='42 Harbour Lane',
                shipping_address_line_2='Suite 7', shipping_city='Portside',
                shipping_state='CA', shipping_postal_code='94000',
                shipping_country='United States',
                subtotal=subtotal, tax=tax, shipping_fee=shipping_fee, total=total,
                shipping_method=ShippingMethod.objects.first(),
                shipping_method_name='Standard shipping',
                payment_method='simulated', payment_status='paid',
                status=final_status, stock_deducted=True,
                created_at=timezone.now() - timedelta(days=days_ago),
            )
            for product in picked:
                OrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    sku=product.sku, quantity=1, unit_price=product.effective_price,
                    total_price=product.effective_price,
                )
            OrderStatusUpdate.objects.create(
                order=order, from_status='', to_status=OrderStatus.PENDING,
                changed_by=customer, note='Order placed.',
                created_at=order.created_at,
            )
            progression = [OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
                           OrderStatus.SHIPPED, OrderStatus.DELIVERED]
            stop_at = progression.index(final_status)
            for step_status in progression[:stop_at + 1]:
                OrderStatusUpdate.objects.create(
                    order=order, to_status=step_status, changed_by=admin,
                    note='Seed history',
                    created_at=order.created_at + timedelta(hours=2),
                )
