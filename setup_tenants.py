import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'easymbstore.settings')
django.setup()

from tenants.models import Shop, Domain
from django.core.management import call_command
from django.contrib.auth.models import User

def setup_tenants():
    print("Migrating shared apps...")
    call_command('migrate_schemas', '--shared')

    print("Creating public tenant...")
    # Create the public tenant if it doesn't exist
    public_shop, created = Shop.objects.get_or_create(
        schema_name='public',
        defaults={'name': 'Public Schema'}
    )

    # Create the domain for public tenant
    Domain.objects.get_or_create(
        domain='localhost', # Default domain for local testing
        tenant=public_shop,
        defaults={'is_primary': True}
    )

    print("Creating 5 shops...")
    for i in range(1, 6):
        shop_schema = f'shop{i}'
        shop_name = f'Shop {i}'
        shop_domain = f'shop{i}'

        print(f"  -> Setting up {shop_name} ({shop_schema})...")
        shop, created = Shop.objects.get_or_create(
            schema_name=shop_schema,
            defaults={'name': shop_name}
        )

        Domain.objects.get_or_create(
            domain=shop_domain,
            tenant=shop,
            defaults={'is_primary': True}
        )

        # Apply migrations for this tenant if not automatically applied
        call_command('migrate_schemas', '--tenant', schema_name=shop_schema)

    print("Tenant setup completed successfully!")

if __name__ == '__main__':
    setup_tenants()
