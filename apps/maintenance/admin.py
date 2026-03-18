from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.maintenance.models import MaintenanceTicket, TicketPhoto, TicketStatusHistory


class TicketPhotoInline(TabularInline):
    model = TicketPhoto
    extra = 0
    fields = ('stage', 'photo', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


class TicketStatusHistoryInline(TabularInline):
    model = TicketStatusHistory
    extra = 0
    fields = ('status', 'changed_by', 'note', 'changed_at')
    readonly_fields = ('changed_at',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(ModelAdmin):
    list_display = ('pk', 'room', 'status', 'reported_by', 'technician', 'created_at')
    list_filter = ('status', 'room__floor__building__dormitory')
    search_fields = ('description', 'room__number', 'technician')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TicketPhotoInline, TicketStatusHistoryInline]
