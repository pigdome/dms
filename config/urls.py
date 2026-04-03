from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from apps.core.sitemaps import StaticViewSitemap


def root_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return redirect('dashboard:index')
    return redirect('core:landing')


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Allow: /$',
        'Allow: /landing',
        'Disallow: /admin/',
        'Disallow: /tenant/',
        'Disallow: /dashboard/',
        'Disallow: /billing/',
        'Disallow: /rooms/',
        'Disallow: /tenants/',
        'Disallow: /maintenance/',
        'Disallow: /notifications/',
        f'Sitemap: {request.build_absolute_uri("/sitemap.xml")}',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


sitemaps = {'static': StaticViewSitemap}

handler404 = 'apps.core.views.custom_404'
handler500 = 'apps.core.views.custom_500'

urlpatterns = [
    path('admin/', admin.site.urls),

    # SEO
    path('robots.txt', robots_txt),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),

    # Root → dashboard or login
    path('', root_redirect, name='home'),

    # Auth + Health check
    path('', include('apps.core.urls')),

    # Dashboard
    path('dashboard/', include('apps.dashboard.urls')),

    # Reports (per-building breakdown) — /reports/ maps to ReportView
    path('reports/', include(('apps.dashboard.report_urls', 'reports'))),

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

    # REST API — /api/bills/, /api/token/
    path('api/', include('apps.billing.api_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
