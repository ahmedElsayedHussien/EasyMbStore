"""
URL configuration for easymbstore project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import FileResponse, HttpResponse
import os

def serve_sw(request):
    """Serve service worker from root scope so it covers the entire app."""
    sw_path = os.path.join(settings.BASE_DIR, 'erp', 'static', 'sw.js')
    with open(sw_path, 'rb') as f:
        content = f.read()
    return HttpResponse(
        content,
        content_type='application/javascript',
        headers={
            'Service-Worker-Allowed': '/',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
    )


def serve_manifest(request):
    """Serve PWA manifest from root."""
    manifest_path = os.path.join(settings.BASE_DIR, 'erp', 'static', 'manifest.json')
    with open(manifest_path, 'rb') as f:
        content = f.read()
    return HttpResponse(
        content,
        content_type='application/manifest+json',
        headers={'Cache-Control': 'no-cache'},
    )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('sw.js', serve_sw, name='service_worker'),
    path('manifest.json', serve_manifest, name='pwa_manifest'),
    path('', include('erp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = 'erp.views.custom_permission_denied_view'

