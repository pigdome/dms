from django.urls import path
from apps.notifications.views import (
    ParcelCreateView,
    ParcelListView,
    BroadcastCreateView,
    BroadcastListView,
    BroadcastPreviewView,
    BroadcastConfirmView,
)

app_name = 'notifications'

urlpatterns = [
    path('parcels/', ParcelCreateView.as_view(), name='parcel_log'),
    path('parcels/history/', ParcelListView.as_view(), name='parcel_list'),
    path('broadcast/', BroadcastCreateView.as_view(), name='broadcast'),
    path('broadcast/list/', BroadcastListView.as_view(), name='broadcast_list'),
    path('broadcast/preview/<int:pk>/', BroadcastPreviewView.as_view(), name='broadcast_preview'),
    path('broadcast/<int:pk>/confirm/', BroadcastConfirmView.as_view(), name='broadcast_confirm'),
]
