"""Payment transaction admin."""
from django.contrib import admin
from django.utils.html import format_html

from ecommerce.admin_site import admin_site

from .models import PaymentTransaction

STATUS_COLORS = {
    'succeeded': '#198754', 'failed': '#b02a37', 'refunded': '#6f42c1',
    'cancelled': '#6c757d', 'pending': '#997400', 'initiated': '#0d6efd',
}


@admin.register(PaymentTransaction, site=admin_site)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order_link', 'gateway', 'amount', 'currency',
                    'status_badge', 'transaction_id', 'created_at')
    list_filter = ('gateway', 'status', 'created_at')
    search_fields = ('reference', 'transaction_id', 'order__order_number',
                     'order__user__email')
    readonly_fields = ('reference', 'order', 'amount', 'currency', 'gateway',
                       'status', 'transaction_id', 'gateway_response',
                       'failure_reason', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            STATUS_COLORS.get(obj.status, '#000'), obj.get_status_display(),
        )

    @admin.display(description='Order')
    def order_link(self, obj):
        return format_html(
            '<a href="/admin/orders/order/{}/change/">{}</a>',
            obj.order.pk, obj.order.order_number,
        )
