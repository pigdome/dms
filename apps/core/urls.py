from django.urls import path
from apps.core.views import landing_view, login_view, logout_view, SetupWizardView, property_switch_view, theme_toggle_view

app_name = 'core'

urlpatterns = [
    path('welcome/', landing_view, name='landing'),
    path('login/', login_view, name='login'),

    path('logout/', logout_view, name='logout'),
    path('setup/', SetupWizardView.as_view(), name='setup_wizard'),
    path('property/switch/', property_switch_view, name='property_switch'),
    path('theme/toggle/', theme_toggle_view, name='theme_toggle'),
]
