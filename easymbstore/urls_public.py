from django.contrib import admin
from django.urls import path
from django.http import HttpResponse

def public_home(request):
    return HttpResponse('<html dir="rtl"><body><h1>مرحباً بك في النظام المركزي (Public Schema)</h1><p><a href="/admin/">الدخول للوحة الإدارة</a></p></body></html>')

urlpatterns = [
    path('', public_home, name='public_home'),
    path('admin/', admin.site.urls),
]
