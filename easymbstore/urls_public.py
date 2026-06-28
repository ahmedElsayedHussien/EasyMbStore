from django.contrib import admin
from django.urls import path
from django.http import HttpResponse
from django.conf import settings
import os

def serve_sw(request):
    sw_path = os.path.join(settings.BASE_DIR, 'erp', 'static', 'sw.js')
    if not os.path.exists(sw_path):
        return HttpResponse('Service Worker not found', status=404)
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
    manifest_path = os.path.join(settings.BASE_DIR, 'erp', 'static', 'manifest.json')
    if not os.path.exists(manifest_path):
        return HttpResponse('Manifest not found', status=404)
    with open(manifest_path, 'rb') as f:
        content = f.read()
    return HttpResponse(
        content,
        content_type='application/manifest+json',
        headers={'Cache-Control': 'no-cache'},
    )

def public_home(request):
    return HttpResponse('<html dir="rtl"><body><h1>مرحباً بك في النظام المركزي (Public Schema)</h1><p><a href="/admin/">الدخول للوحة الإدارة</a></p></body></html>')

urlpatterns = [
    path('', public_home, name='public_home'),
    path('admin/', admin.site.urls),
    path('sw.js', serve_sw, name='public_service_worker'),
    path('manifest.json', serve_manifest, name='public_pwa_manifest'),
]
