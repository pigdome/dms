from django.urls import path
from apps.notifications.views import (
    ParcelCreateView,
    ParcelListView,
    BroadcastCreateView,
)

app_name = 'notifications'

urlpatterns = [
    path('parcels/', ParcelCreateView.as_view(), name='parcel_log'),
    path('parcels/history/', ParcelListView.as_view(), name='parcel_list'),
    path('broadcast/', BroadcastCreateView.as_view(), name='broadcast'),
]
