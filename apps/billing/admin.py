from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.billing.models import Bill, BillingSettings, Payment


class PaymentInline(TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('tmr_ref', 'amount', 'paid_at', 'idempotency_key')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BillingSettings)
class BillingSettingsAdmin(ModelAdmin):
    list_display = ('dormitory', 'bill_day', 'grace_days', 'elec_rate', 'water_rate', 'dunning_enabled')
    search_fields = ('dormitory__name',)


@admin.register(Bill)
class BillAdmin(ModelAdmin):
    list_display = ('invoice_number', 'room', 'month', 'total', 'status', 'due_date')
    list_filter = ('status', 'month', 'room__floor__building__dormitory')
    search_fields = ('invoice_number', 'room__number', 'room__floor__building__dormitory__name')
    readonly_fields = ('invoice_number', 'created_at', 'updated_at')
    date_hierarchy = 'month'
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ('bill', 'amount', 'tmr_ref', 'paid_at')
    search_fields = ('tmr_ref', 'idempotency_key', 'bill__invoice_number')
    readonly_fields = ('tmr_ref', 'idempotency_key', 'webhook_payload', 'paid_at', 'created_at')

    def has_add_permission(self, request):
        return False
