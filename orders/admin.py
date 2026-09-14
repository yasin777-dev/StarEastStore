"""Order, item, coupon and shipping admin (sections 13-14)."""
from django.contrib import admin
from django.utils.html import format_html

from ecommerce.admin_site import admin_site

from .services import set_order_status
from .models import (
    Coupon, Order, OrderItem, OrderStatus, OrderStatusUpdate,
    PaymentStatus, ShippingMethod,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_link', 'variant_name', 'sku', 'quantity',
                       'unit_price', 'total_price')
    fields = ('product_link', 'variant_name', 'sku', 'quantity',
              'unit_price', 'total_price')
    can_delete = False

    @admin.display(description='Product')
    def product_link(self, obj):
        if obj.product:
            return format_html('<a href="{}">{}</a>', f'/admin/products/product/{obj.product.pk}/change/',
                               obj.product_name)
        return obj.product_name


class OrderStatusInline(admin.TabularInline):
    model = OrderStatusUpdate
    extra = 0
    readonly_fields = ('order', 'from_status', 'to_status', 'note', 'changed_by', 'created_at')
    can_delete = False


@admin.register(Order, site=admin_site)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'created_at', 'status',
                    'payment_status', 'payment_method', 'total')
    list_filter = ('status', 'payment_status', 'payment_method', 'created_at')
    search_fields = ('order_number', 'user__email', 'email',
                     'shipping_full_name', 'shipping_city')
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    readonly_fields = ('order_number', 'user', 'email', 'subtotal', 'discount',
                       'tax', 'shipping_fee', 'total', 'coupon',
                       'shipping_method_name', 'created_at', 'updated_at',
                       'stock_deducted')
    inlines = [OrderItemInline, OrderStatusInline]
    list_per_page = 25
    actions = [
        'action_confirm', 'action_process', 'action_ship', 'action_deliver',
        'action_cancel', 'action_refund',
    ]

    fieldsets = (
        ('Order', {'fields': ('order_number', 'user', 'email', 'status',
                              'payment_status', 'payment_method', 'stock_deducted')}),
        ('Money', {'fields': ('subtotal', 'discount', 'tax', 'shipping_fee', 'total', 'coupon')}),
        ('Shipping', {'fields': ('shipping_full_name', 'shipping_phone',
                                 'shipping_address_line_1', 'shipping_address_line_2',
                                 'shipping_city', 'shipping_state', 'shipping_postal_code',
                                 'shipping_country', 'shipping_method_name')}),
        ('Meta', {'fields': ('customer_note', 'created_at', 'updated_at'),
                  'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        """Status edits from the admin page trigger the notification flow."""
        if change and 'status' in form.changed_data:
            new_status = form.cleaned_data['status']
            # Save other fields first without touching status flow:
            obj.save()
            set_order_status(obj, new_status, changed_by=request.user,
                             note='Updated from admin panel')
            return
        super().save_model(request, obj, form, change)

    def _bulk_status(self, request, queryset, status: str):
        for order in queryset:
            set_order_status(order, status, changed_by=request.user,
                             note=f'Bulk action: {status}')
        self.message_user(request, f'{queryset.count()} order(s) updated to "{status}".')

    @admin.action(description='Mark as confirmed')
    def action_confirm(self, request, queryset):
        self._bulk_status(request, queryset, OrderStatus.CONFIRMED)

    @admin.action(description='Mark as processing')
    def action_process(self, request, queryset):
        self._bulk_status(request, queryset, OrderStatus.PROCESSING)

    @admin.action(description='Mark as shipped (emails customer)')
    def action_ship(self, request, queryset):
        self._bulk_status(request, queryset, OrderStatus.SHIPPED)

    @admin.action(description='Mark as delivered (emails customer, COD becomes paid)')
    def action_deliver(self, request, queryset):
        for order in queryset:
            if order.payment_method == 'cod' and order.payment_status == PaymentStatus.COD_PENDING:
                order.payment_status = PaymentStatus.PAID
                order.save(update_fields=['payment_status', 'updated_at'])
            set_order_status(order, OrderStatus.DELIVERED, changed_by=request.user,
                             note='Delivered')
        self.message_user(request, 'Orders delivered.')

    @admin.action(description='Cancel order (restores stock)')
    def action_cancel(self, request, queryset):
        from .services import cancel_order, CheckoutError

        for order in queryset:
            try:
                cancel_order(order, changed_by=request.user)
            except CheckoutError:
                pass
        self.message_user(request, 'Cancellation attempted for selected orders.')

    @admin.action(description='Mark as refunded (restores stock)')
    def action_refund(self, request, queryset):
        from .services import restore_order_stock

        for order in queryset:
            restore_order_stock(order)
            if order.payment_status == PaymentStatus.PAID:
                order.payment_status = PaymentStatus.REFUNDED
            order.status = OrderStatus.REFUNDED
            order.save(update_fields=['status', 'payment_status', 'updated_at'])
            OrderStatusUpdate.objects.create(
                order=order, from_status=order.status, to_status=OrderStatus.REFUNDED,
                changed_by=request.user, note='Refunded from admin',
            )
        self.message_user(request, 'Orders marked as refunded.')


@admin.register(ShippingMethod, site=admin_site)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'estimated_delivery', 'is_active', 'sort_order')
    list_editable = ('price', 'is_active', 'sort_order')
    search_fields = ('name',)


@admin.register(Coupon, site=admin_site)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_display', 'minimum_order_amount',
                    'maximum_discount', 'usage_summary', 'valid_from',
                    'valid_until', 'is_active')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)
    readonly_fields = ('used_count',)

    @admin.display(description='Discount')
    def discount_display(self, obj):
        if obj.discount_type == Coupon.DiscountType.PERCENTAGE:
            return f'{obj.discount_value}%'
        return f'{obj.discount_value}'

    @admin.display(description='Usage')
    def usage_summary(self, obj):
        limit = obj.usage_limit if obj.usage_limit is not None else '∞'
        return f'{obj.used_count} / {limit}'


@admin.register(OrderItem, site=admin_site)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'variant_name', 'sku',
                    'quantity', 'unit_price', 'total_price')
    search_fields = ('order__order_number', 'product_name', 'sku')
    list_select_related = ('order',)
