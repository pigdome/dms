from django.urls import path
from apps.dashboard.views import ReportView

urlpatterns = [
    path('', ReportView.as_view(), name='index'),
]
