"""Review admin."""
from django.contrib import admin

from ecommerce.admin_site import admin_site

from .models import Review


@admin.register(Review, site=admin_site)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'title', 'is_verified_purchase',
                    'created_at', 'updated_at')
    list_filter = ('rating', 'is_verified_purchase', 'created_at')
    search_fields = ('product__name', 'user__email', 'title', 'text')
    list_select_related = ('product', 'user')
    readonly_fields = ('created_at', 'updated_at')
