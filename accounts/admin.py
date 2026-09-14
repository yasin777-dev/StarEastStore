"""Admin for users, profiles and addresses (section 13)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from ecommerce.admin_site import admin_site

from .models import Address, CustomerProfile, User


@admin.register(User, site=admin_site)
class UserAdmin(BaseUserAdmin):
    ordering = ('-date_joined',)
    list_display = ('email', 'username', 'first_name', 'last_name',
                    'phone', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'phone')
    readonly_fields = ('last_login', 'date_joined')
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser',
                                    'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2',
                       'is_staff', 'is_superuser'),
        }),
    )


@admin.register(CustomerProfile, site=admin_site)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'date_of_birth', 'created_at', 'updated_at')
    search_fields = ('user__email', 'user__username', 'phone')
    list_select_related = ('user',)


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ('full_name', 'phone', 'address_line_1', 'city', 'state',
              'postal_code', 'country', 'is_default')
    show_change_link = True


UserAdmin.inlines = [AddressInline]


@admin.register(Address, site=admin_site)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'city', 'state', 'country',
                    'postal_code', 'is_default')
    list_filter = ('country', 'is_default', 'city')
    search_fields = ('full_name', 'user__email', 'address_line_1', 'city', 'postal_code')
    list_select_related = ('user',)
