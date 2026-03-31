"""
API URL patterns สำหรับ billing module
mount ที่ config/urls.py เป็น /api/
"""
from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from apps.billing.api import BillListAPIView, BillDetailAPIView

urlpatterns = [
    # Token endpoint — POST /api/token/ ด้วย username+password เพื่อรับ token
    path('token/', obtain_auth_token, name='api_token'),

    # Bill endpoints — scoped ด้วย dormitory ของ token owner เสมอ
    path('bills/', BillListAPIView.as_view(), name='api_bill_list'),
    path('bills/<uuid:pk>/', BillDetailAPIView.as_view(), name='api_bill_detail'),
]
