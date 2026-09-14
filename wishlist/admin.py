"""Wishlist admin."""
from django.contrib import admin

from ecommerce.admin_site import admin_site

from .models import WishlistItem


@admin.register(WishlistItem, site=admin_site)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    search_fields = ('user__email', 'product__name')
    list_select_related = ('user', 'product')
