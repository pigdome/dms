from django.urls import path
from apps.dashboard.views import DashboardView, ReportView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardView.as_view(), name='index'),
    path('reports/', ReportView.as_view(), name='reports'),
]
