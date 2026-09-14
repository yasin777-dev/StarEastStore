from django.contrib import admin

from ecommerce.admin_site import admin_site

from .models import ContactMessage


@admin.register(ContactMessage, site=admin_site)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at', 'is_handled')
    list_filter = ('is_handled', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('name', 'email', 'subject', 'message', 'created_at')
    list_editable = ('is_handled',)
    date_hierarchy = 'created_at'
