from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
from .models import Shop, Domain

class DomainInline(admin.TabularInline):
    model = Domain
    max_num = 1

@admin.register(Shop)
class ShopAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('schema_name', 'name', 'created_on')
    search_fields = ('schema_name', 'name')
    inlines = [DomainInline]

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    search_fields = ('domain', 'tenant__schema_name')
