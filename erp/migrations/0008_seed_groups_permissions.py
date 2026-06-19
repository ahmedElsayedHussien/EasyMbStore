# -*- coding: utf-8 -*-
from django.db import migrations

def create_groups_and_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    
    # 1. إنشاء المجموعات الأربعة الأساسية
    manager_group, _ = Group.objects.get_or_create(name='المدير العام')
    cashier_group, _ = Group.objects.get_or_create(name='الكاشير والمبيعات')
    tech_group, _ = Group.objects.get_or_create(name='فني الصيانة')
    inventory_group, _ = Group.objects.get_or_create(name='أمين المخزن')
    
    # 2. توزيع الصلاحيات
    # المدير العام يحصل على كافة صلاحيات التطبيق
    all_erp_perms = Permission.objects.filter(content_type__app_label='erp')
    manager_group.permissions.set(all_erp_perms)
    
    # الكاشير
    cashier_codenames = [
        'add_saleinvoice', 'view_saleinvoice', 'add_saleitem', 'view_saleitem',
        'add_payment', 'view_payment', 'add_device', 'view_device', 'add_deviceattachment',
        'add_contact', 'view_contact', 'add_cashshift', 'change_cashshift', 'view_cashshift',
        'add_expense', 'view_expense', 'view_warranty', 'view_product', 'view_warehouse'
    ]
    cashier_perms = Permission.objects.filter(content_type__app_label='erp', codename__in=cashier_codenames)
    cashier_group.permissions.set(cashier_perms)
    
    # فني الصيانة
    tech_codenames = [
        'view_repairticket', 'change_repairticket', 'add_repairticket', 'add_repairpartused', 'view_repairpartused',
        'view_product', 'view_stock', 'view_device', 'view_warehouse', 'view_contact'
    ]
    tech_perms = Permission.objects.filter(content_type__app_label='erp', codename__in=tech_codenames)
    tech_group.permissions.set(tech_perms)
    
    # أمين المخزن
    inventory_codenames = [
        'add_purchaseinvoice', 'view_purchaseinvoice', 'add_purchaseitem', 'view_purchaseitem',
        'add_stocktransfer', 'change_stocktransfer', 'view_stocktransfer', 'add_stocktransferitem', 'view_stocktransferitem',
        'view_product', 'view_stock', 'view_device', 'view_warehouse', 'view_contact'
    ]
    inventory_perms = Permission.objects.filter(content_type__app_label='erp', codename__in=inventory_codenames)
    inventory_group.permissions.set(inventory_perms)

def remove_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['المدير العام', 'الكاشير والمبيعات', 'فني الصيانة', 'أمين المخزن']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('erp', '0007_alter_cashshift_options_alter_contact_options_and_more'),
    ]

    operations = [
        migrations.RunPython(create_groups_and_permissions, reverse_code=remove_groups),
    ]
