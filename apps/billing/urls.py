from django.urls import path

from apps.billing.views import BillingSettingsView, BillListView, BillDetailView, tmr_webhook

app_name = 'billing'

urlpatterns = [
    path('', BillListView.as_view(), name='list'),
    path('<int:pk>/', BillDetailView.as_view(), name='detail'),
    path('settings/', BillingSettingsView.as_view(), name='settings'),
    path('webhook/tmr/', tmr_webhook, name='tmr_webhook'),
]
