from django.urls import path
from apps.tenants.views import (
    TenantListView,
    TenantDetailView,
    TenantCreateView,
    TenantUpdateView,
    AnonymizeTenantView,
    OcrIdCardView,
)

app_name = 'tenants'

urlpatterns = [
    path('', TenantListView.as_view(), name='list'),
    path('add/', TenantCreateView.as_view(), name='create'),
    path('<uuid:pk>/', TenantDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', TenantUpdateView.as_view(), name='update'),
    # PDPA Right to be Forgotten — owner only, irreversible
    path('<uuid:pk>/anonymize/', AnonymizeTenantView.as_view(), name='anonymize'),
    # N1: OCR stub endpoint
    path('ocr-id-card/', OcrIdCardView.as_view(), name='ocr_id_card'),
]
