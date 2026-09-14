"""DRF serializers - never expose private user information."""
from rest_framework import serializers

from orders.models import Order
from products.models import Brand, Category, Product, ProductVariant
from reviews.models import Review
from wishlist.models import WishlistItem


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'is_active', 'product_count']


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'description', 'logo', 'is_active', 'product_count']


class ProductImageSerializer(serializers.Serializer):
    url = serializers.SerializerMethodField()
    alt_text = serializers.CharField()
    is_primary = serializers.BooleanField()

    def get_url(self, obj) -> str | None:
        return obj.image.url if obj.image else None


class ProductVariantSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(source='is_in_stock', read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'size', 'color', 'display_name', 'sku', 'effective_price',
                  'stock_quantity', 'in_stock']


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    brand = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(source='is_in_stock', read_only=True)
    image = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'sku', 'category', 'brand', 'price',
                  'sale_price', 'effective_price', 'is_on_sale', 'in_stock',
                  'stock_quantity', 'featured', 'image', 'average_rating',
                  'total_sales', 'created_at']

    def get_image(self, obj) -> str | None:
        image = obj.primary_image()
        return image.image.url if image and image.image else None

    def get_average_rating(self, obj) -> float | None:
        data = obj.rating_summary()
        return data['average']


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(source='images.all', many=True, read_only=True)
    variants = ProductVariantSerializer(source='active_variant_list', many=True, read_only=True)
    description = serializers.CharField()
    short_description = serializers.CharField()
    rating = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'description', 'short_description', 'images', 'variants', 'rating',
        ]

    def get_rating(self, obj) -> dict:
        return obj.rating_summary()


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()
    product_slug = serializers.SlugRelatedField(
        source='product', slug_field='slug', read_only=True,
    )

    class Meta:
        model = Review
        fields = ['id', 'product_slug', 'rating', 'title', 'text',
                  'reviewer', 'is_verified_purchase', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified_purchase']

    def get_reviewer(self, obj) -> str:
        # Public display name only - no emails in the API.
        return obj.reviewer_name


class ReviewCreateSerializer(ReviewSerializer):
    product_slug = serializers.SlugField(write_only=True)

    class Meta(ReviewSerializer.Meta):
        read_only_fields = ReviewSerializer.Meta.read_only_fields + ['reviewer']

    def validate_rating(self, value):
        if not 1 <= int(value) <= 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value


class OrderItemSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    variant_name = serializers.CharField()
    sku = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['order_number', 'customer', 'status', 'payment_status',
                  'payment_method', 'subtotal', 'discount', 'tax', 'shipping_fee',
                  'total', 'shipping_address_one_line', 'items', 'created_at']
        read_only_fields = fields

    def get_customer(self, obj) -> str:
        # Public-safe: order number owner only sees their own orders anyway.
        return obj.shipping_full_name


class CartLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    product_name = serializers.CharField()
    variant_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    product_url = serializers.CharField()
    in_stock = serializers.BooleanField()


class CartSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    lines = CartLineSerializer(many=True)


class WishlistSerializer(serializers.ModelSerializer):
    product_slug = serializers.SlugRelatedField(source='product', slug_field='slug', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    effective_price = serializers.DecimalField(
        source='product.effective_price', max_digits=10, decimal_places=2, read_only=True,
    )

    class Meta:
        model = WishlistItem
        fields = ['id', 'product_slug', 'product_name', 'effective_price', 'created_at']
