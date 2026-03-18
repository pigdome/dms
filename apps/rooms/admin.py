from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.rooms.models import Building, Floor, MeterReading, Room


class FloorInline(TabularInline):
    model = Floor
    extra = 0
    fields = ('number',)


class RoomInline(TabularInline):
    model = Room
    extra = 0
    fields = ('number', 'base_rent', 'status')


@admin.register(Building)
class BuildingAdmin(ModelAdmin):
    list_display = ('name', 'dormitory', 'created_at')
    list_filter = ('dormitory',)
    search_fields = ('name', 'dormitory__name')
    inlines = [FloorInline]


@admin.register(Floor)
class FloorAdmin(ModelAdmin):
    list_display = ('__str__', 'building', 'number')
    list_filter = ('building__dormitory', 'building')
    search_fields = ('building__name',)
    inlines = [RoomInline]


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    list_display = ('number', 'floor', 'base_rent', 'status')
    list_filter = ('status', 'floor__building__dormitory', 'floor__building')
    search_fields = ('number', 'floor__building__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MeterReading)
class MeterReadingAdmin(ModelAdmin):
    list_display = ('room', 'reading_date', 'elec_curr', 'water_curr', 'recorded_by')
    list_filter = ('room__floor__building__dormitory', 'reading_date')
    search_fields = ('room__number',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'reading_date'
