from django.urls import path

from apps.billing.views import (
    BillingSettingsView, BillListView, BillDetailView,
    BillCSVExportView, BillQRRedirectView, tmr_webhook
)

app_name = 'billing'

urlpatterns = [
    path('', BillListView.as_view(), name='list'),
    path('export/', BillCSVExportView.as_view(), name='export'),
    path('<uuid:pk>/', BillDetailView.as_view(), name='detail'),
    path('settings/', BillingSettingsView.as_view(), name='settings'),
    path('webhook/tmr/', tmr_webhook, name='tmr_webhook'),
    # B3 fix: QR redirect ผ่าน server — ไม่ expose tmr_api_key ใน client URL
    path('qr/<uuid:bill_id>/', BillQRRedirectView.as_view(), name='qr_redirect'),
]
