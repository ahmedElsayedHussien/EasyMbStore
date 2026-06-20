from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from decimal import Decimal
from erp.models import (
    StoreSetting, Contact, Warehouse, Product, Stock, Device,
    ExpenseCategory, CashShift
)

class Command(BaseCommand):
    help = 'Seeds initial demo data for the Mobile POS and ERP system'

    def handle(self, *args, **options):
        self.stdout.write('Seeding initial data...')

        # تهيئة الصلاحيات والمجموعات أولاً
        self.stdout.write('Setting up Groups and Permissions...')
        manager_group, _ = Group.objects.get_or_create(name='المدير العام')
        cashier_group, _ = Group.objects.get_or_create(name='الكاشير والمبيعات')
        tech_group, _ = Group.objects.get_or_create(name='فني الصيانة')
        inventory_group, _ = Group.objects.get_or_create(name='أمين المخزن')
        
        # جلب الصلاحيات وربطها بالمجموعات
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
        
        # الفني
        tech_codenames = [
            'view_repairticket', 'change_repairticket', 'add_repairticket', 'add_repairpartused', 'view_repairpartused',
            'view_product', 'view_warehouse', 'view_contact'
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
        self.stdout.write(self.style.SUCCESS('Groups and Permissions set up successfully.'))

        # 1. إنشاء مستخدم رئيسي (Superuser) وتأكيد صلاحياته
        admin_user, admin_created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@easymb.com'})
        if admin_created:
            admin_user.set_password('admin123')
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()
        if admin_created:
            self.stdout.write(self.style.SUCCESS('Superuser created: username="admin", password="admin123"'))
        else:
            self.stdout.write('Superuser "admin" verified and updated.')

        # مستخدمو التجربة للأدوار - إعادة تعيين المجموعات والصلاحيات لضمان صحة الاختبار
        cashier_user, cashier_created = User.objects.get_or_create(username='cashier', defaults={'email': 'cashier@easymb.com'})
        if cashier_created:
            cashier_user.set_password('cashier123')
        cashier_user.is_superuser = False
        cashier_user.is_staff = False
        cashier_user.groups.set([cashier_group])
        cashier_user.user_permissions.clear() # إزالة الصلاحيات المخصصة الفردية إن وجدت
        cashier_user.save()
        self.stdout.write(self.style.SUCCESS('User set up: cashier / cashier123 (Cashier/POS)'))
            
        tech_user, tech_created = User.objects.get_or_create(username='technician', defaults={'email': 'tech@easymb.com'})
        if tech_created:
            tech_user.set_password('tech123')
        tech_user.is_superuser = False
        tech_user.is_staff = False
        tech_user.groups.set([tech_group])
        tech_user.user_permissions.clear()
        tech_user.save()
        self.stdout.write(self.style.SUCCESS('User set up: technician / tech123 (Technician)'))
            
        stock_user, stock_created = User.objects.get_or_create(username='inventory', defaults={'email': 'inventory@easymb.com'})
        if stock_created:
            stock_user.set_password('stock123')
        stock_user.is_superuser = False
        stock_user.is_staff = False
        stock_user.groups.set([inventory_group])
        stock_user.user_permissions.clear()
        stock_user.save()
        self.stdout.write(self.style.SUCCESS('User set up: inventory / stock123 (Stock Manager)'))

        # 2. إنشاء إعدادات المحل (Singleton)
        setting, created = StoreSetting.objects.get_or_create(
            id=1,
            defaults={
                'store_name': 'إيزي إم بي ستور (EasyMB Store)',
                'receipt_header': 'مرحباً بكم في إيزي إم بي ستور\nأفضل خيارات الموبايل والصيانة بالضمان القانوني\nهاتف: 01020304050',
                'receipt_footer': 'شكراً لتعاملكم معنا!\nالاستبدال والاسترجاع خلال 14 يوماً بموجب إيصال الشراء.\nالضمان لا يغطي سوء الاستخدام أو كسر الشاشة.',
                'whatsapp_api_key': 'mock_whatsapp_key_xyz_123',
                'sms_api_key': 'mock_sms_key_abc_456'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Store settings seeded.'))

        # 3. إنشاء الفروع والمخازن
        showroom, _ = Warehouse.objects.get_or_create(name='المعرض (صالة العرض)')
        main_wh, _ = Warehouse.objects.get_or_create(name='المخزن الرئيسي (الدعم)')
        self.stdout.write(self.style.SUCCESS('Warehouses created.'))

        # 4. إنشاء جهات الاتصال الأساسية
        cash_cust, _ = Contact.objects.get_or_create(
            phone='01000000000',
            defaults={
                'name': 'عميل نقدي',
                'contact_type': 'customer'
            }
        )
        
        supplier_corp, _ = Contact.objects.get_or_create(
            phone='01111111111',
            defaults={
                'name': 'الشركة المتحدة لتوريدات الهواتف',
                'contact_type': 'supplier',
                'address': 'وسط البلد، القاهرة'
            }
        )
        
        used_sell, _ = Contact.objects.get_or_create(
            phone='01222222222',
            defaults={
                'name': 'أحمد محمود صالح',
                'contact_type': 'used_seller',
                'national_id': '29510150102456',
                'address': 'شارع الجلاء، القاهرة'
            }
        )
        self.stdout.write(self.style.SUCCESS('Contacts seeded.'))

        # 5. إنشاء المنتجات (هواتف، إكسسوارات، قطع غيار)
        phone_15pro, _ = Product.objects.get_or_create(
            barcode_qr='111111',
            defaults={
                'name': 'iPhone 15 Pro Max 256GB',
                'product_type': 'phone',
                'selling_price': Decimal('55000.00'),
                'average_cost': Decimal('50000.00'),
                'requires_imei': True
            }
        )
        
        phone_s24, _ = Product.objects.get_or_create(
            barcode_qr='222222',
            defaults={
                'name': 'Samsung Galaxy S24 Ultra',
                'product_type': 'phone',
                'selling_price': Decimal('52000.00'),
                'average_cost': Decimal('47000.00'),
                'requires_imei': True
            }
        )
        
        charger, _ = Product.objects.get_or_create(
            barcode_qr='333333',
            defaults={
                'name': 'شاحن سريع Apple USB-C 20W',
                'product_type': 'accessory',
                'selling_price': Decimal('900.00'),
                'average_cost': Decimal('600.00'),
                'requires_imei': False
            }
        )
        
        screen_15p, _ = Product.objects.get_or_create(
            barcode_qr='444444',
            defaults={
                'name': 'شاشة iPhone 15 Pro كوري الأصلي',
                'product_type': 'spare_part',
                'selling_price': Decimal('6500.00'),
                'average_cost': Decimal('5000.00'),
                'requires_imei': False
            }
        )
        self.stdout.write(self.style.SUCCESS('Products seeded.'))

        # 6. إضافة مخزون ابتدائي للأصناف السائبة
        Stock.objects.get_or_create(product=charger, warehouse=showroom, defaults={'quantity': 50})
        Stock.objects.get_or_create(product=charger, warehouse=main_wh, defaults={'quantity': 100})
        Stock.objects.get_or_create(product=screen_15p, warehouse=showroom, defaults={'quantity': 10})
        Stock.objects.get_or_create(product=screen_15p, warehouse=main_wh, defaults={'quantity': 25})
        self.stdout.write(self.style.SUCCESS('Bulk stocks updated.'))

        # 7. إضافة هواتف مسيرنة ابتدائية متاحة للبيع
        Device.objects.get_or_create(
            imei='IMEI123456789012345',
            defaults={
                'product': phone_15pro,
                'condition': 'new',
                'warehouse': showroom,
                'is_sold': False,
                'cost': Decimal('50000.00')
            }
        )
        
        Device.objects.get_or_create(
            imei='IMEI987654321098765',
            defaults={
                'product': phone_s24,
                'condition': 'new',
                'warehouse': showroom,
                'is_sold': False,
                'cost': Decimal('47000.00')
            }
        )

        # إضافة جهاز مستعمل تم شراؤه مسبقاً وجاهز للبيع (أو للاستبدال)
        Device.objects.get_or_create(
            imei='IMEI_USED_IPH15_999',
            defaults={
                'product': phone_15pro,
                'condition': 'used',
                'warehouse': showroom,
                'is_sold': False,
                'cost': Decimal('35000.00'),
                'purchased_from': used_sell
            }
        )
        self.stdout.write(self.style.SUCCESS('Serialized devices seeded.'))

        # 8. بنود المصروفات
        ExpenseCategory.objects.get_or_create(name='شاي وضيافة')
        ExpenseCategory.objects.get_or_create(name='كهرباء ومياه وغاز')
        ExpenseCategory.objects.get_or_create(name='أدوات ومستلزمات مكتبية')
        ExpenseCategory.objects.get_or_create(name='إيجار المحل')
        ExpenseCategory.objects.get_or_create(name='أجور عمالة إضافية')
        self.stdout.write(self.style.SUCCESS('Expense categories seeded.'))

        self.stdout.write(self.style.SUCCESS('Database seeding finished successfully!'))
