from django.urls import path

from apps.maintenance.views import TenantTicketCreateView
from apps.tenants.views import TenantHomeView, TenantBillsView, TenantBillDetailView, TenantParcelsView, TenantProfileView

app_name = 'tenant'

urlpatterns = [
    path('home/', TenantHomeView.as_view(), name='home'),
    path('bills/', TenantBillsView.as_view(), name='bills'),
    path('bills/<uuid:pk>/', TenantBillDetailView.as_view(), name='bill_detail'),
    path('parcels/', TenantParcelsView.as_view(), name='parcels'),
    path('profile/', TenantProfileView.as_view(), name='profile'),
    path('maintenance/', TenantTicketCreateView.as_view(), name='maintenance'),
]
