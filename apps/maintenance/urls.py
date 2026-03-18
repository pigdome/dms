from django.urls import path
from apps.maintenance.views import (
    TicketListView,
    TicketDetailView,
    TicketCreateView,
    update_status,
)

app_name = 'maintenance'

urlpatterns = [
    path('', TicketListView.as_view(), name='list'),
    path('create/', TicketCreateView.as_view(), name='create'),
    path('<int:pk>/', TicketDetailView.as_view(), name='detail'),
    path('<int:pk>/update-status/', update_status, name='update_status'),
]
