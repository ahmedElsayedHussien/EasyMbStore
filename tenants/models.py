from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Shop(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "المتجر / الفرع"
        verbose_name_plural = "المتاجر والفروع"

class Domain(DomainMixin):
    class Meta:
        verbose_name = "النطاق (Domain)"
        verbose_name_plural = "النطاقات (Domains)"
