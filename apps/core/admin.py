from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.models import ActivityLog, CustomUser, Dormitory, UserDormitoryRole


class UserDormitoryRoleInline(TabularInline):
    model = UserDormitoryRole
    extra = 0
    fields = ('dormitory', 'role', 'is_primary')


@admin.register(Dormitory)
class DormitoryAdmin(ModelAdmin):
    list_display = ('name', 'address', 'invoice_prefix', 'created_at')
    search_fields = ('name', 'address')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ('username', 'email', 'get_full_name', 'role', 'dormitory', 'is_active')
    list_filter = ('role', 'is_active', 'dormitory')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)

    fieldsets = UserAdmin.fieldsets + (
        ('DMS Role', {'fields': ('role', 'dormitory')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('DMS Role', {'fields': ('role', 'dormitory')}),
    )
    inlines = [UserDormitoryRoleInline]


@admin.register(UserDormitoryRole)
class UserDormitoryRoleAdmin(ModelAdmin):
    list_display = ('user', 'dormitory', 'role', 'is_primary')
    list_filter = ('role', 'dormitory')
    search_fields = ('user__username', 'dormitory__name')


@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ('created_at', 'user', 'dormitory', 'action')
    list_filter = ('dormitory',)
    search_fields = ('action', 'user__username')
    readonly_fields = ('created_at', 'user', 'dormitory', 'action', 'detail')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
