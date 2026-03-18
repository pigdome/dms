from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.notifications.models import Broadcast, DunningLog, Parcel


@admin.register(Parcel)
class ParcelAdmin(ModelAdmin):
    list_display = ('room', 'carrier', 'logged_by', 'notified_at', 'created_at')
    list_filter = ('room__floor__building__dormitory',)
    search_fields = ('carrier', 'notes', 'room__number')
    readonly_fields = ('created_at',)


@admin.register(Broadcast)
class BroadcastAdmin(ModelAdmin):
    list_display = ('title', 'dormitory', 'audience_type', 'sent_by', 'sent_at')
    list_filter = ('dormitory', 'audience_type')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at', 'sent_at')


@admin.register(DunningLog)
class DunningLogAdmin(ModelAdmin):
    list_display = ('bill', 'trigger_type', 'success', 'sent_at')
    list_filter = ('trigger_type', 'success')
    search_fields = ('bill__invoice_number',)
    readonly_fields = ('sent_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
