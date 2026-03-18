from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.tenants.models import DigitalVault, Lease, TenantProfile


class LeaseInline(TabularInline):
    model = Lease
    extra = 0
    fields = ('room', 'status', 'start_date', 'end_date')
    readonly_fields = ('created_at',)


class DigitalVaultInline(TabularInline):
    model = DigitalVault
    extra = 0
    fields = ('file_type', 'file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


@admin.register(TenantProfile)
class TenantProfileAdmin(ModelAdmin):
    list_display = ('user', 'phone', 'line_id', 'active_room', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [LeaseInline, DigitalVaultInline]

    @admin.display(description='Active Room')
    def active_room(self, obj):
        return obj.active_room


@admin.register(Lease)
class LeaseAdmin(ModelAdmin):
    list_display = ('tenant', 'room', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'room__floor__building__dormitory')
    search_fields = ('tenant__user__username', 'room__number')
    readonly_fields = ('created_at',)
