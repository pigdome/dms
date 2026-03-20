from django.urls import path
from apps.rooms.views import (
    RoomListView,
    RoomDetailView,
    RoomCreateView,
    RoomUpdateView,
    MeterReadingCreateView,
)

app_name = 'rooms'

urlpatterns = [
    path('', RoomListView.as_view(), name='list'),
    path('create/', RoomCreateView.as_view(), name='create'),
    path('<uuid:pk>/', RoomDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', RoomUpdateView.as_view(), name='update'),
    path('meter-reading/', MeterReadingCreateView.as_view(), name='meter_reading'),
]
