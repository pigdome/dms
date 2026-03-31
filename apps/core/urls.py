from django.urls import path
from apps.core.views import (
    landing_view, login_view, logout_view, SetupWizardView,
    property_switch_view, theme_toggle_view, AuditLogView,
    ImportRoomsView, ImportTenantsView,
)

app_name = 'core'

urlpatterns = [
    path('welcome/', landing_view, name='landing'),
    path('login/', login_view, name='login'),

    path('logout/', logout_view, name='logout'),
    path('setup/', SetupWizardView.as_view(), name='setup_wizard'),
    path('property/switch/', property_switch_view, name='property_switch'),
    path('theme/toggle/', theme_toggle_view, name='theme_toggle'),
    path('audit-log/', AuditLogView.as_view(), name='audit_log'),

    # Data Import Wizard
    path('import/rooms/', ImportRoomsView.as_view(), name='import_rooms'),
    path('import/tenants/', ImportTenantsView.as_view(), name='import_tenants'),
]
