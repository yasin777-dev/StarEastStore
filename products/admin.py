from django.contrib import admin
"""Product admin with inline images and variants (section 13)."""

from ecommerce.admin_site import admin_site

from .models import Brand, Category, Product, ProductImage, ProductVariant


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'display_order')
    readonly_fields = ('thumbnail',)

    @admin.display(description='Preview')
    def thumbnail(self, obj):
        if obj.image:
            from django.utils.html import format_html

            return format_html(
                '<img src="{}" style="max-height:60px;border-radius:4px;" />',
                obj.image.url,
            )
        return '-'


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ('size', 'color', 'sku', 'price', 'stock_quantity', 'is_active')


@admin.register(Product, site=admin_site)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'thumbnail', 'name', 'sku', 'category', 'brand', 'price',
        'sale_price', 'stock_level', 'is_active', 'featured', 'total_sales',
    )
    list_filter = ('is_active', 'featured', 'category', 'brand', 'created_at')
    list_editable = ('is_active', 'featured')
    search_fields = ('name', 'sku', 'description', 'brand__name', 'category__name')
    list_select_related = ('category', 'brand')
    autocomplete_fields = ('category', 'brand')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline, ProductVariantInline]
    readonly_fields = ('total_sales', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    list_per_page = 25
    actions = ['make_active', 'make_inactive', 'make_featured', 'remove_featured']

    fieldsets = (
        ('Basic information', {
            'fields': ('name', 'slug', 'sku', 'category', 'brand'),
        }),
        ('Description', {'fields': ('short_description', 'description')}),
        ('Pricing', {'fields': ('price', 'sale_price')}),
        ('Inventory', {'fields': ('stock_quantity', 'low_stock_threshold')}),
        ('Visibility', {'fields': ('is_active', 'featured')}),
        ('Statistics', {'fields': ('total_sales',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Image', ordering='name')
    def thumbnail(self, obj):
        image = obj.primary_image()
        if image and image.image:
            from django.utils.html import format_html

            return format_html(
                '<img src="{}" style="max-height:42px;border-radius:4px;" />',
                image.image.url,
            )
        return '—'

    @admin.display(description='Stock', ordering='stock_quantity')
    def stock_level(self, obj):
        if obj.stock_quantity == 0:
            from django.utils.html import format_html

            return format_html('<span style="color:#b02a37">Out of stock</span>')
        if obj.stock_quantity <= obj.low_stock_threshold:
            from django.utils.html import format_html

            return format_html(
                '<span style="color:#997400">Low ({})</span>', obj.stock_quantity,
            )
        return obj.stock_quantity

    @admin.action(description='Mark selected products active')
    def make_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='Mark selected products inactive')
    def make_inactive(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description='Mark selected products featured')
    def make_featured(self, request, queryset):
        queryset.update(featured=True)

    @admin.action(description='Remove featured flag')
    def remove_featured(self, request, queryset):
        queryset.update(featured=False)


@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'product_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Products')
    def product_count(self, obj):
        return obj.products.filter(is_active=True).count()


@admin.register(Brand, site=admin_site)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'product_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}

    @admin.display(description='Products')
    def product_count(self, obj):
        return obj.products.filter(is_active=True).count()
