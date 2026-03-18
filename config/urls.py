from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


def root_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return redirect('dashboard:index')
    return redirect('core:login')


urlpatterns = [
    path('admin/', admin.site.urls),

    # Root → dashboard or login
    path('', root_redirect, name='home'),

    # Auth
    path('', include('apps.core.urls')),

    # Dashboard
    path('dashboard/', include('apps.dashboard.urls')),

    # Rooms & meter readings
    path('rooms/', include('apps.rooms.urls')),

    # Tenants — owner manages tenant records
    path('tenants/', include('apps.tenants.urls')),

    # Tenant self-service portal
    path('tenant/', include('apps.tenants.tenant_urls')),

    # Maintenance
    path('maintenance/', include('apps.maintenance.urls')),

    # Notifications (parcels + broadcast)
    path('notifications/', include('apps.notifications.urls')),

    # Billing
    path('billing/', include('apps.billing.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
