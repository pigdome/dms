from django.urls import path

from apps.billing.views import BillingSettingsView, tmr_webhook

app_name = 'billing'

urlpatterns = [
    path('settings/', BillingSettingsView.as_view(), name='settings'),
    path('webhook/tmr/', tmr_webhook, name='tmr_webhook'),
]
