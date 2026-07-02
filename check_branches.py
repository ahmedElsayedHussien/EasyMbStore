import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "easymbstore.settings")
django.setup()

from django_tenants.utils import schema_context
from erp.models import Branch
from tenants.models import Shop

for client in Shop.objects.all():
    print(f"Schema: {client.schema_name}")
    with schema_context(client.schema_name):
        try:
            count = Branch.objects.count()
            print(f"  Branch count: {count}")
        except Exception as e:
            print(f"  Error: {e}")
