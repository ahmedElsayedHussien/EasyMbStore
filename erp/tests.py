from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from erp.models import (
    StoreSetting, Contact, Warehouse, Product, Stock, Device,
    PurchaseInvoice, PurchaseItem, SaleInvoice, SaleItem, Payment,
    StockTransfer, StockTransferItem, RepairTicket, RepairPartUsed, CashShift, Expense, ExpenseCategory
)

class ERPBusinessLogicTests(TestCase):
    def setUp(self):
        # 1. Create User / Cashier
        self.user = User.objects.create_user(username='cashier1', password='password123')
        
        # 2. Create Warehouses
        self.showroom = Warehouse.objects.create(name='المعرض', is_active=True)
        self.main_wh = Warehouse.objects.create(name='المخزن الرئيسي', is_active=True)
        
        # 3. Create Contacts
        self.supplier = Contact.objects.create(name='شركة الموردين', phone='01011111111', contact_type='supplier')
        self.customer = Contact.objects.create(name='عميل تجريبي', phone='01222222222', contact_type='customer')
        
        # 4. Create Products
        self.bulk_accessory = Product.objects.create(
            name='جراب سيليكون آيفون',
            barcode_qr='ACC123',
            product_type='accessory',
            average_cost=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            requires_imei=False
        )
        
        self.serialized_phone = Product.objects.create(
            name='آيفون 15 برو',
            barcode_qr='IPH15P',
            product_type='phone',
            average_cost=Decimal('40000.00'),
            selling_price=Decimal('45000.00'),
            requires_imei=True
        )

    def test_moving_average_cost_and_stock_on_purchase(self):
        """
        تغيير متوسط التكلفة المتحرك وتحديث كميات المخازن عند إنشاء فاتورة مشتريات.
        """
        # إنشاء فاتورة شراء لـ 10 جرابات بسعر 60 جنيه للواحد
        # المخزون الحالي: 0، التكلفة الحالية: 50.00
        invoice = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('600.00'),
            discount=Decimal('0.00'),
            deduction_addition_tax=Decimal('6.00'), # 1% خصم وإضافة
            net_amount=Decimal('594.00')
        )
        
        PurchaseItem.objects.create(
            invoice=invoice,
            product=self.bulk_accessory,
            warehouse=self.showroom,
            quantity=10,
            unit_cost=Decimal('60.00')
        )
        
        # التحقق من تحديث كمية المخزن
        stock = Stock.objects.get(product=self.bulk_accessory, warehouse=self.showroom)
        self.assertEqual(stock.quantity, 10)
        
        # التحقق من حساب متوسط التكلفة الجديد:
        # (0 * 50 + 10 * 60) / 10 = 60.00
        self.bulk_accessory.refresh_from_db()
        self.assertEqual(self.bulk_accessory.average_cost, Decimal('60.00'))

        # فاتورة ثانية لـ 5 جرابات بسعر 45 جنيه للواحد
        # المتوسط الجديد المتوقع: (10 * 60 + 5 * 45) / 15 = (600 + 225) / 15 = 825 / 15 = 55.00
        invoice2 = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('225.00'),
            net_amount=Decimal('225.00')
        )
        
        PurchaseItem.objects.create(
            invoice=invoice2,
            product=self.bulk_accessory,
            warehouse=self.showroom,
            quantity=5,
            unit_cost=Decimal('45.00')
        )
        
        self.bulk_accessory.refresh_from_db()
        self.assertEqual(self.bulk_accessory.average_cost, Decimal('55.00'))
        
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 15)

    def test_serialized_device_creation_on_purchase(self):
        """
        التحقق من إنشاء أجهزة بالـ IMEI المقابل عند شراء هواتف.
        """
        invoice = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('135000.00'),
            net_amount=Decimal('135000.00')
        )
        
        # شراء هاتفين أحاديي السيريال وهاتف ثنائي السيريال (عبر الـ slash)
        PurchaseItem.objects.create(
            invoice=invoice,
            product=self.serialized_phone,
            warehouse=self.showroom,
            quantity=3,
            unit_cost=Decimal('45000.00'),
            imei_list="IMEI111, IMEI222, IMEI333/IMEI333_2",
            storage="256",
            ram="8",
            is_tax_paid=True
        )
        
        # يجب أن ينشأ 3 سجلات في جدول Device
        devices = Device.objects.filter(product=self.serialized_phone)
        self.assertEqual(devices.count(), 3)
        
        device1 = Device.objects.get(imei='IMEI111')
        self.assertEqual(device1.warehouse, self.showroom)
        self.assertEqual(device1.cost, Decimal('45000.00'))
        self.assertFalse(device1.is_sold)
        self.assertEqual(device1.purchased_from, self.supplier)
        self.assertEqual(device1.storage, '256')
        self.assertEqual(device1.ram, '8')
        self.assertTrue(device1.is_tax_paid)

        # التحقق من الهاتف ثنائي السيريال
        device3 = Device.objects.get(imei='IMEI333')
        self.assertEqual(device3.imei2, 'IMEI333_2')
        self.assertEqual(device3.warehouse, self.showroom)
        self.assertEqual(device3.cost, Decimal('45000.00'))
        self.assertEqual(device3.storage, '256')
        self.assertEqual(device3.ram, '8')
        self.assertTrue(device3.is_tax_paid)

    def test_sales_pos_stock_deduction(self):
        """
        التحقق من خصم المخزون للبضائع السائبة وتعليم الأجهزة كمباعة عند عمل فاتورة بيع.
        """
        # أولاً: إضافة بضاعة للمخزن
        Stock.objects.create(product=self.bulk_accessory, warehouse=self.showroom, quantity=20)
        device = Device.objects.create(
            product=self.serialized_phone,
            imei='IMEI777',
            condition='new',
            warehouse=self.showroom,
            is_sold=False,
            cost=Decimal('40000.00')
        )
        
        # فتح وردية للكاشير
        shift = CashShift.objects.create(cashier=self.user, opening_balance=Decimal('1000.00'))
        
        # إنشاء فاتورة بيع
        invoice = SaleInvoice.objects.create(
            shift=shift,
            cashier=self.user,
            customer=self.customer,
            total_amount=Decimal('45100.00'),
            net_amount=Decimal('45100.00')
        )
        
        # بيع جراب وهاتف
        SaleItem.objects.create(
            invoice=invoice,
            product=self.bulk_accessory,
            warehouse=self.showroom,
            quantity=2,
            unit_price=Decimal('100.00')
        )
        
        SaleItem.objects.create(
            invoice=invoice,
            product=self.serialized_phone,
            warehouse=self.showroom,
            device=device,
            quantity=1,
            unit_price=Decimal('45000.00')
        )
        
        # التحقق من خصم المخزون
        stock = Stock.objects.get(product=self.bulk_accessory, warehouse=self.showroom)
        self.assertEqual(stock.quantity, 18) # 20 - 2 = 18
        
        device.refresh_from_db()
        self.assertTrue(device.is_sold)

    def test_trade_in_device_handling(self):
        """
        التحقق من إرجاع أو إدخال الجهاز المستبدل إلى المخزون وتخصيص بياناته.
        """
        # إنشاء وردية
        shift = CashShift.objects.create(cashier=self.user, opening_balance=Decimal('1000.00'))
        
        # إنشاء جهاز مستعمل سيقوم العميل باستبداله
        # (ملاحظة: نقوم بإنشائه كجهاز مباع أو ننشئ سجل جديد في قاعدة البيانات)
        traded_device = Device.objects.create(
            product=self.serialized_phone,
            imei='IMEI_TRADE_999',
            condition='used',
            warehouse=self.showroom,
            is_sold=True, # نفترض أنه كان مباعاً أو جهازاً خارجياً
            cost=Decimal('0.00')
        )
        
        # فاتورة بيع مع استبدال
        # إجمالي الهاتف الجديد: 45000، العميل سيستبدل هاتفه بـ 15000، الصافي للدفع: 30000
        invoice = SaleInvoice.objects.create(
            shift=shift,
            cashier=self.user,
            customer=self.customer,
            total_amount=Decimal('45000.00'),
            traded_in_device=traded_device,
            trade_in_value=Decimal('15000.00'),
            net_amount=Decimal('30000.00')
        )
        
        # بند البيع للهاتف الجديد
        new_device = Device.objects.create(
            product=self.serialized_phone,
            imei='IMEI_NEW_100',
            condition='new',
            warehouse=self.showroom,
            is_sold=False,
            cost=Decimal('40000.00')
        )
        
        SaleItem.objects.create(
            invoice=invoice,
            product=self.serialized_phone,
            warehouse=self.showroom,
            device=new_device,
            quantity=1,
            unit_price=Decimal('45000.00')
        )
        
        # التحقق من أن الجهاز المستبدل أصبح غير مباع (في حوزة المحل) وتكلفته تساوي قيمة الاستبدال ومخزنه هو المعرض
        traded_device.refresh_from_db()
        self.assertFalse(traded_device.is_sold)
        self.assertEqual(traded_device.cost, Decimal('15000.00'))
        self.assertEqual(traded_device.condition, 'used')
        self.assertEqual(traded_device.warehouse, self.showroom)
        self.assertEqual(traded_device.purchased_from, self.customer)

    def test_stock_transfer_logic(self):
        """
        التحقق من حركات نقل المخزون بين المستودعات عند اكتمال الطلب.
        """
        # إضافة كمية للمخزن الرئيسي
        Stock.objects.create(product=self.bulk_accessory, warehouse=self.main_wh, quantity=50)
        
        # إنشاء هاتف في المخزن الرئيسي
        device = Device.objects.create(
            product=self.serialized_phone,
            imei='IMEI_TRANSFER_888',
            condition='new',
            warehouse=self.main_wh,
            is_sold=False,
            cost=Decimal('40000.00')
        )
        
        # إنشاء حركة تحويل (Pending)
        transfer = StockTransfer.objects.create(
            from_warehouse=self.main_wh,
            to_warehouse=self.showroom,
            created_by=self.user,
            status='pending'
        )
        
        item_bulk = StockTransferItem.objects.create(
            transfer=transfer,
            product=self.bulk_accessory,
            quantity=10
        )
        
        item_device = StockTransferItem.objects.create(
            transfer=transfer,
            product=self.serialized_phone,
            device=device,
            quantity=1
        )
        
        # التحقق من عدم تغير المخزون والفرع وهي pending
        stock_main = Stock.objects.get(product=self.bulk_accessory, warehouse=self.main_wh)
        self.assertEqual(stock_main.quantity, 50)
        
        device.refresh_from_db()
        self.assertEqual(device.warehouse, self.main_wh)
        
        # تحويل الحالة إلى Completed
        transfer.status = 'completed'
        transfer.save()
        
        # التحقق من تعديل المخزون للمستودعين
        stock_main.refresh_from_db()
        self.assertEqual(stock_main.quantity, 40) # 50 - 10
        
        stock_showroom = Stock.objects.get(product=self.bulk_accessory, warehouse=self.showroom)
        self.assertEqual(stock_showroom.quantity, 10) # 0 + 10
        
        # التحقق من تعديل مخزن الهاتف
        device.refresh_from_db()
        self.assertEqual(device.warehouse, self.showroom)

    def test_cash_shift_expected_balance_calculations(self):
        """
        التحقق من حساب الرصيد المتوقع في الخزينة عند المبيعات النقدية والمصروفات.
        """
        shift = CashShift.objects.create(cashier=self.user, opening_balance=Decimal('1000.00'))
        self.assertEqual(shift.expected_closing_balance, Decimal('1000.00'))
        
        # فاتورة مبيعات
        invoice = SaleInvoice.objects.create(
            shift=shift,
            cashier=self.user,
            customer=self.customer,
            total_amount=Decimal('500.00'),
            net_amount=Decimal('500.00')
        )
        
        # دفع نقدي
        payment_cash = Payment.objects.create(
            invoice=invoice,
            payment_method='cash',
            amount=Decimal('300.00')
        )
        
        # دفع فيزا (لا يدخل في رصيد درج الكاشير النقدي)
        payment_visa = Payment.objects.create(
            invoice=invoice,
            payment_method='visa',
            amount=Decimal('200.00')
        )
        
        shift.refresh_from_db()
        # الرصيد المتوقع = 1000 (البداية) + 300 (نقدي) = 1300
        self.assertEqual(shift.expected_closing_balance, Decimal('1300.00'))
        
        # إضافة مصروف
        category = ExpenseCategory.objects.create(name='شاي وضيافة')
        Expense.objects.create(
            shift=shift,
            category=category,
            amount=Decimal('50.00'),
            description='مصاريف ضيافة'
        )
        
        shift.refresh_from_db()
        # الرصيد المتوقع = 1300 - 50 = 1250
        self.assertEqual(shift.expected_closing_balance, Decimal('1250.00'))

    def test_maintenance_parts_deduction(self):
        """
        التحقق من خصم قطع الغيار من المخزن عند استخدامها في تذكرة الصيانة.
        """
        # إضافة قطع غيار للمخزن المعرض
        spare_part = Product.objects.create(
            name='شاشة آيفون 15',
            barcode_qr='SP15SC',
            product_type='spare_part',
            average_cost=Decimal('500.00'),
            selling_price=Decimal('1000.00'),
            requires_imei=False
        )
        Stock.objects.create(product=spare_part, warehouse=self.showroom, quantity=5)
        
        # تذكرة صيانة
        ticket = RepairTicket.objects.create(
            customer=self.customer,
            technician=self.user,
            device_model='آيفون 15 برو',
            issue_description='شاشة مكسورة',
            status='in_progress',
            labor_cost=Decimal('200.00')
        )
        
        # استخدام قطعة الغيار
        RepairPartUsed.objects.create(
            ticket=ticket,
            product=spare_part,
            warehouse=self.showroom,
            quantity=1,
            price=Decimal('1000.00')
        )
        
        # التحقق من خصم المخزون
        stock = Stock.objects.get(product=spare_part, warehouse=self.showroom)
        self.assertEqual(stock.quantity, 4) # 5 - 1

    def test_purchase_invoice_payment_options(self):
        """
        التحقق من خيارات الدفع المختلفة (كاش، آجل، مسدد جزئياً) لعملية الشراء في قاعدة البيانات.
        """
        # 1. فاتورة كاش (كامل المبلغ مدفوع)
        invoice_cash = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('1000.00'),
            net_amount=Decimal('1000.00'),
            payment_method='cash',
            paid_amount=Decimal('1000.00')
        )
        self.assertEqual(invoice_cash.paid_amount, Decimal('1000.00'))
        self.assertEqual(invoice_cash.remaining_amount, Decimal('0.00'))

        # 2. فاتورة آجل (المدفوع 0)
        invoice_credit = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('2000.00'),
            net_amount=Decimal('2000.00'),
            payment_method='credit',
            paid_amount=Decimal('0.00')
        )
        self.assertEqual(invoice_credit.paid_amount, Decimal('0.00'))
        self.assertEqual(invoice_credit.remaining_amount, Decimal('2000.00'))

        # 3. فاتورة مسددة جزئياً
        invoice_partial = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('3000.00'),
            net_amount=Decimal('3000.00'),
            payment_method='partial',
            paid_amount=Decimal('1200.00')
        )
        self.assertEqual(invoice_partial.paid_amount, Decimal('1200.00'))
        self.assertEqual(invoice_partial.remaining_amount, Decimal('1800.00'))


class ERPPermissionsTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group, Permission
        # Create standard groups and permissions
        self.cashier_group, _ = Group.objects.get_or_create(name='الكاشير والمبيعات')
        self.tech_group, _ = Group.objects.get_or_create(name='فني الصيانة')
        
        # Bind permissions
        add_invoice_perm = Permission.objects.get(codename='add_saleinvoice')
        add_device_perm = Permission.objects.get(codename='add_device')
        view_ticket_perm = Permission.objects.get(codename='view_repairticket')
        view_shift_perm = Permission.objects.get(codename='view_cashshift')
        
        self.cashier_group.permissions.add(add_invoice_perm, add_device_perm, view_shift_perm)
        self.tech_group.permissions.add(view_ticket_perm)
        
        # Create test users
        self.cashier_user = User.objects.create_user(username='cashier_test', password='password123')
        self.cashier_user.groups.add(self.cashier_group)
        
        self.tech_user = User.objects.create_user(username='tech_test', password='password123')
        self.tech_user.groups.add(self.tech_group)

    def test_cashier_permissions(self):
        """
        التحقق من أن الكاشير يستطيع الدخول للـ POS ولكن الفني يمنع (403).
        """
        # Cashier login
        self.client.login(username='cashier_test', password='password123')
        
        # open shift first because views check it, wait, pos_view requires active shift or redirects to shift_manage
        # and shift_manage requires view_cashshift. Wait! In tests, let's see if pos_view checks permission first.
        # Yes, permission_required decorator runs first.
        # Let's request pos_view
        response = self.client.get('/pos/')
        # Should redirect (302) to shift_manage because cashier has no open shift, but not 403!
        self.assertEqual(response.status_code, 302)
        
        # Logout cashier
        self.client.logout()
        
        # Tech login
        self.client.login(username='tech_test', password='password123')
        
        response = self.client.get('/pos/')
        # Should return 403 Forbidden because tech does not have add_saleinvoice permission
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'خطأ 403 - وصول غير مصرح به', status_code=403)
        self.assertContains(response, 'إنشاء فواتير البيع (نقطة البيع) [erp.add_saleinvoice]', status_code=403)

    def test_technician_permissions(self):
        """
        التحقق من أن الفني يستطيع الدخول لقائمة الصيانة ولكن الكاشير يمنع (403) إذا لم يكن لديه صلاحية.
        """
        # Tech login
        self.client.login(username='tech_test', password='password123')
        
        response = self.client.get('/repairs/')
        # Should return 200 OK since tech has view_repairticket permission
        self.assertEqual(response.status_code, 200)
        
        # Logout tech
        self.client.logout()
        
        # Cashier login
        self.client.login(username='cashier_test', password='password123')
        
        response = self.client.get('/repairs/')
        # Should return 403 Forbidden because cashier does not have view_repairticket permission
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'خطأ 403 - وصول غير مصرح به', status_code=403)
        self.assertContains(response, 'عرض تذاكر الصيانة [erp.view_repairticket]', status_code=403)

    def test_role_redirection_from_dashboard(self):
        """
        التحقق من توجيه الكاشير والفني تلقائياً عند طلب صفحة لوحة التحكم الرئيسية.
        """
        from django.contrib.auth.models import Permission
        change_ticket_perm = Permission.objects.get(codename='change_repairticket')
        self.tech_group.permissions.add(change_ticket_perm)

        # 1. Tech redirection to repairs
        self.client.login(username='tech_test', password='password123')
        response = self.client.get('/')
        self.assertRedirects(response, '/repairs/')
        self.client.logout()

        # 2. Cashier redirection to POS
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/pos/')

    def test_cannot_open_multiple_shifts_simultaneously(self):
        """
        التحقق من عدم السماح للكاشير بفتح وردية جديدة إذا كان لديه وردية مفتوحة بالفعل.
        """
        self.client.login(username='cashier_test', password='password123')
        
        # فتح وردية أولى
        response = self.client.post('/shifts/', {'opening_balance': '1000.00'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CashShift.objects.filter(cashier=self.cashier_user, status='open').count(), 1)
        
        # محاولة فتح وردية ثانية بينما الأولى مفتوحة
        response_dup = self.client.post('/shifts/', {'opening_balance': '500.00'})
        self.assertEqual(response_dup.status_code, 200)
        
        # التأكد من أنه لم يفتح وردية ثانية مفتوحة
        self.assertEqual(CashShift.objects.filter(cashier=self.cashier_user, status='open').count(), 1)

    def test_cashier_expense_restriction(self):
        """
        التحقق من حجب تسجيل المصروفات وقائمة المصروفات عن الكاشير (غير المسؤول) 
        وإظهارها للمسؤولين (is_staff/is_superuser).
        """
        from erp.models import CashShift, ExpenseCategory
        # 1. تهيئة وردية للكاشير
        shift = CashShift.objects.create(cashier=self.cashier_user, opening_balance=Decimal('1000.00'), status='open')
        
        # 2. تسجيل دخول الكاشير وطلب صفحة الوردية
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get('/shifts/')
        self.assertEqual(response.status_code, 200)
        
        # يجب ألا يحتوي الرد على نصوص تسجيل المصروفات أو جدولها
        self.assertNotContains(response, 'تسجيل مصروف تشغيلي من الدرج')
        self.assertNotContains(response, 'قائمة المصروفات التشغيلية بالوردية')
        
        # محاولة إرسال مصروف عبر AJAX ككاشير
        category = ExpenseCategory.objects.create(name='ضيافة')
        response_post = self.client.post('/shifts/add-expense/', {
            'category': category.id,
            'amount': '50.00',
            'description': 'شاي'
        })
        # يجب أن يرجع 403 Forbidden
        self.assertEqual(response_post.status_code, 403)
        self.client.logout()
        
        # 3. تسجيل دخول مستخدم مسؤول (admin/is_staff)
        admin_user = User.objects.create_superuser(username='admin_test', password='password123', email='admin@test.com')
        self.client.login(username='admin_test', password='password123')
        
        admin_shift = CashShift.objects.create(cashier=admin_user, opening_balance=Decimal('2000.00'), status='open')
        
        response_admin = self.client.get('/shifts/')
        self.assertEqual(response_admin.status_code, 200)
        
        # يجب أن يحتوي الرد على نصوص تسجيل المصروفات والجدول
        self.assertContains(response_admin, 'تسجيل مصروف تشغيلي من الدرج')
        self.assertContains(response_admin, 'قائمة المصروفات التشغيلية بالوردية')
        
        # المسؤول يستطيع تسجيل مصروف بنجاح
        response_admin_post = self.client.post('/shifts/add-expense/', {
            'category': category.id,
            'amount': '50.00',
            'description': 'شاي'
        })
        self.assertEqual(response_admin_post.status_code, 200)
        self.client.logout()

    def test_contact_validation(self):
        """
        التحقق من صحة التحقق من رقم الهاتف والرقم القومي.
        """
        from django.core.exceptions import ValidationError
        
        # رقم هاتف صحيح (11 رقم) ورقم قومي صحيح (14 رقم)
        contact1 = Contact(name="عميل صحيح", phone="01234567890", contact_type="customer", national_id="12345678901234")
        try:
            contact1.full_clean()
        except ValidationError:
            self.fail("فشل التحقق من بيانات العميل الصحيح.")
            
        # رقم هاتف غير صحيح (أقل من 11)
        contact2 = Contact(name="عميل هاتف قصير", phone="0123456", contact_type="customer")
        with self.assertRaises(ValidationError):
            contact2.full_clean()
            
        # رقم هاتف غير صحيح (أكثر من 11)
        contact3 = Contact(name="عميل هاتف طويل", phone="01234567890123", contact_type="customer")
        with self.assertRaises(ValidationError):
            contact3.full_clean()

        # رقم هاتف يحتوي على أحرف
        contact4 = Contact(name="عميل هاتف غير رقمي", phone="01234567abc", contact_type="customer")
        with self.assertRaises(ValidationError):
            contact4.full_clean()
            
        # رقم قومي غير صحيح (أقل من 14)
        contact5 = Contact(name="عميل قومي قصير", phone="01234567891", contact_type="used_seller", national_id="12345")
        with self.assertRaises(ValidationError):
            contact5.full_clean()

        # رقم قومي غير صحيح (أكثر من 14)
        contact6 = Contact(name="عميل قومي طويل", phone="01234567892", contact_type="used_seller", national_id="1234567890123456")
        with self.assertRaises(ValidationError):
            contact6.full_clean()

    def test_quick_add_product_view(self):
        """
        التحقق من صحة إضافة منتج جديد بسرعة عبر الـ AJAX view.
        """
        import json
        self.client.login(username='cashier_test', password='password123')
        
        # إضافة ناجحة
        payload = {
            'name': 'آيفون 16 برو',
            'barcode_qr': 'IPH16P_TEST',
            'selling_price': '60000.00'
        }
        response = self.client.post(
            '/products/quick-add/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.content)
        self.assertEqual(res_data['status'], 'success')
        self.assertEqual(res_data['name'], 'آيفون 16 برو')
        
        # التحقق من وجوده بقاعدة البيانات كصنف يتطلب IMEI ونوع هاتف
        new_prod = Product.objects.get(id=res_data['id'])
        self.assertEqual(new_prod.barcode_qr, 'IPH16P_TEST')
        self.assertTrue(new_prod.requires_imei)
        self.assertEqual(new_prod.product_type, 'phone')
        
        # إضافة فاشلة لتكرار الباركود
        response_dup = self.client.post(
            '/products/quick-add/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response_dup.status_code, 400)
        res_dup_data = json.loads(response_dup.content)
        self.assertIn('error', res_dup_data)

    def test_duplicate_imei_prevention_on_used_purchase(self):
        """
        التحقق من منع شراء جهاز مستعمل بسيريال IMEI مكرر وعرض رابط التاريخ.
        """
        # تهيئة البيانات
        self.client.login(username='cashier_test', password='password123')
        warehouse = Warehouse.objects.create(name='المعرض الرئيسي', is_active=True)
        product = Product.objects.create(
            name='آيفون 15',
            barcode_qr='IPH15_TEST_DUP',
            product_type='phone',
            selling_price=Decimal('40000.00'),
            requires_imei=True
        )
        
        # إنشاء جهاز موجود بالفعل
        existing_device = Device.objects.create(
            product=product,
            imei='999998888877777',
            condition='used',
            warehouse=warehouse,
            cost=Decimal('30000.00'),
            storage='256',
            ram='8',
            is_tax_paid=True
        )

        # محاولة تسجيل شراء جهاز مستعمل جديد بنفس السيريال
        payload = {
            'name': 'بائع تجريبي جديد',
            'phone': '01122334455',
            'national_id': '11223344556677',
            'address': 'العنوان',
            'product': product.id,
            'imei': '999998888877777',  # نفس السيريال المكرر
            'imei2': '',
            'warehouse': warehouse.id,
            'cost': '35000.00',
            'storage': '256',
            'ram': '8',
            'used_status': 'like_new',
            'notes': 'ملاحظات تجربة التكرار',
            'attachments-TOTAL_FORMS': '0',
            'attachments-INITIAL_FORMS': '0',
        }
        
        response = self.client.post('/used-purchase/', data=payload)
        self.assertEqual(response.status_code, 200)  # يعيد رندرة الصفحة ولا ينشئ جهاز
        
        # التحقق من أن عدد الأجهزة لم يزداد
        self.assertEqual(Device.objects.filter(imei='999998888877777').count(), 1)
        
        # التحقق من وجود رسالة الخطأ والرابط
        messages = list(response.context['messages'])
        self.assertTrue(len(messages) > 0)
        error_msg = str(messages[0])
        self.assertIn("تنبيه: يوجد جهاز بالفعل مسجل بهذا السيريال", error_msg)
        self.assertIn(f"/devices/{existing_device.pk}/history/", error_msg)

    def test_device_history_view_and_tax_status(self):
        """
        التحقق من عمل صفحة تقرير تاريخ الجهاز وعرض تفاصيل مواصفاته وحالة الضريبة.
        """
        self.client.login(username='cashier_test', password='password123')
        warehouse = Warehouse.objects.create(name='المعرض الرئيسي', is_active=True)
        product = Product.objects.create(
            name='سامسونج S24',
            barcode_qr='SAMS24_TEST',
            product_type='phone',
            selling_price=Decimal('50000.00'),
            requires_imei=True
        )
        
        # جهاز خالص الضريبة ومساحة 1 جيجا
        device = Device.objects.create(
            product=product,
            imei='555554444433333',
            condition='used',
            warehouse=warehouse,
            cost=Decimal('35000.00'),
            storage='1gb',  # المساحة المضافة الجديدة
            ram='12',
            used_status='good_condition',
            is_tax_paid=True, # خالص الضريبة
            notes='تجربة مواصفات وضريبة'
        )
        
        response = self.client.get(f'/devices/{device.pk}/history/')
        self.assertEqual(response.status_code, 200)
        
        self.assertContains(response, 'سامسونج S24')
        self.assertContains(response, '555554444433333')
        self.assertContains(response, '1 جيجا')
        self.assertContains(response, '12 رام')
        self.assertContains(response, 'خالص الضريبة')
        self.assertContains(response, 'تجربة مواصفات وضريبة')

    def test_out_of_stock_products_hidden_in_pos(self):
        """
        التحقق من إخفاء المنتجات التي نفذت كميتها (الأجهزة المباعة أو الإكسسوارات صفرية المخزن) من شاشة البيع.
        """
        self.client.login(username='cashier_test', password='password123')
        warehouse = Warehouse.objects.create(name='المعرض الرئيسي', is_active=True)
        
        # 1. صنف هاتف مباع بالكامل
        phone_product = Product.objects.create(
            name='هاتف مباع بالكامل',
            barcode_qr='PHONE_SOLD_OUT',
            product_type='phone',
            selling_price=Decimal('10000.00'),
            requires_imei=True
        )
        # جهاز مباع
        Device.objects.create(
            product=phone_product,
            imei='111122223333444',
            condition='used',
            warehouse=warehouse,
            cost=Decimal('8000.00'),
            is_sold=True  # مباع
        )

        # 2. صنف هاتف متوفر منه نسخة واحدة
        phone_available = Product.objects.create(
            name='هاتف متاح للبيع',
            barcode_qr='PHONE_AVAILABLE',
            product_type='phone',
            selling_price=Decimal('15000.00'),
            requires_imei=True
        )
        Device.objects.create(
            product=phone_available,
            imei='555566667777888',
            condition='used',
            warehouse=warehouse,
            cost=Decimal('12000.00'),
            is_sold=False  # غير مباع
        )

        # 3. صنف إكسسوار كميته صفر
        acc_sold_out = Product.objects.create(
            name='جراب نافذ الكمية',
            barcode_qr='ACC_SOLD_OUT',
            product_type='accessory',
            selling_price=Decimal('150.00'),
            requires_imei=False
        )
        # لا ننشئ له سجل Stock أو ننشئه بكمية 0
        Stock.objects.create(product=acc_sold_out, warehouse=warehouse, quantity=0)

        # 4. صنف إكسسوار متوفر
        acc_available = Product.objects.create(
            name='جراب متاح للبيع',
            barcode_qr='ACC_AVAILABLE',
            product_type='accessory',
            selling_price=Decimal('200.00'),
            requires_imei=False
        )
        Stock.objects.create(product=acc_available, warehouse=warehouse, quantity=10)

        # فتح وردية أولاً لتجنب التحويل التلقائي
        CashShift.objects.create(cashier=self.cashier_user, opening_balance=Decimal('1000.00'))

        # طلب شاشة البيع
        response = self.client.get('/pos/')
        self.assertEqual(response.status_code, 200)

        # يجب أن تحتوي الصفحة على المنتجات المتاحة
        self.assertContains(response, 'هاتف متاح للبيع')
        self.assertContains(response, 'جراب متاح للبيع')

        # يجب ألا تحتوي الصفحة على المنتجات التي نفذت كميتها
        self.assertNotContains(response, 'هاتف مباع بالكامل')
        self.assertNotContains(response, 'جراب نافذ الكمية')

    def test_pos_product_grid_htmx_search_and_category_filtering(self):
        """
        التحقق من عمل البحث والتصفية الديناميكية بقاعدة البيانات عبر HTMX.
        """
        self.client.login(username='cashier_test', password='password123')
        warehouse = Warehouse.objects.create(name='المعرض الرئيسي', is_active=True)
        
        # إنشاء منتجات مختلفة للتصفية والبحث
        phone1 = Product.objects.create(name='شاومي نوت 13', barcode_qr='XIAOMI13', product_type='phone', selling_price=Decimal('12000.00'), requires_imei=True)
        Device.objects.create(product=phone1, imei='XIAOMI_IMEI_111', condition='used', warehouse=warehouse, cost=Decimal('10000.00'))

        phone2 = Product.objects.create(name='أوبو رينو 11', barcode_qr='OPPO11', product_type='phone', selling_price=Decimal('18000.00'), requires_imei=True)
        Device.objects.create(product=phone2, imei='OPPO_IMEI_222', condition='used', warehouse=warehouse, cost=Decimal('15000.00'))

        acc1 = Product.objects.create(name='شاحن شاومي الأصلي', barcode_qr='XIAOMI_CHARGER', product_type='accessory', selling_price=Decimal('500.00'), requires_imei=False)
        Stock.objects.create(product=acc1, warehouse=warehouse, quantity=15)

        # 1. البحث بالنص فقط "شاومي"
        response = self.client.get('/pos/grid/?q=شاومي')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'شاومي نوت 13')
        self.assertContains(response, 'شاحن شاومي الأصلي')
        self.assertNotContains(response, 'أوبو رينو 11')

        # 2. التصفية بالقسم فقط "phone"
        response = self.client.get('/pos/grid/?category=phone')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'شاومي نوت 13')
        self.assertContains(response, 'أوبو رينو 11')
        self.assertNotContains(response, 'شاحن شاومي الأصلي')

        # 3. التصفية المدمجة بالنص والقسم (شاومي + accessory)
        response = self.client.get('/pos/grid/?category=accessory&q=شاومي')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'شاحن شاومي الأصلي')
        self.assertNotContains(response, 'شاومي نوت 13')
        self.assertNotContains(response, 'أوبو رينو 11')

    def test_ajax_create_customer(self):
        """
        التحقق من إنشاء عميل جديد بنجاح عبر AJAX ومنع إدخال بيانات مكررة أو غير صالحة.
        """
        self.client.login(username='cashier_test', password='password123')
        
        # 1. إنشاء عميل ناجح
        payload = {
            'name': 'عميل صيانة تجريبي',
            'phone': '01099999999',
            'national_id': '12345678901234',
            'address': 'القاهرة، مصر'
        }
        response = self.client.post('/contacts/add-ajax/', data=payload)
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertEqual(res_data['customer']['name'], 'عميل صيانة تجريبي')
        self.assertEqual(res_data['customer']['phone'], '01099999999')
        
        # التأكد من حفظ العميل في قاعدة البيانات بنوع جهة اتصال 'customer'
        contact = Contact.objects.get(id=res_data['customer']['id'])
        self.assertEqual(contact.contact_type, 'customer')
        
        # 2. محاولة إدخال رقم هاتف مكرر
        response = self.client.post('/contacts/add-ajax/', data=payload)
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data['status'], 'error')
        self.assertIn('phone', res_data['errors'])

    def test_repair_ticket_form_customer_filtering(self):
        """
        التحقق من أن قائمة العملاء في تذكرة الصيانة لا تظهر الموردين وتظهر فقط العملاء وبائعي المستعمل.
        """
        Contact.objects.create(name='عميل عادي', phone='01111111111', contact_type='customer')
        Contact.objects.create(name='بائع مستعمل', phone='01111111112', contact_type='used_seller')
        Contact.objects.create(name='مورد بضاعة', phone='01111111113', contact_type='supplier')
        
        from erp.forms import RepairTicketForm
        form = RepairTicketForm()
        customers_queryset = form.fields['customer'].queryset
        
        # يجب أن تحتوي القائمة على العميل العادي وبائع المستعمل، ولا تحتوي على مورد البضاعة
        self.assertTrue(customers_queryset.filter(name='عميل عادي').exists())
        self.assertTrue(customers_queryset.filter(name='بائع مستعمل').exists())
        self.assertFalse(customers_queryset.filter(name='مورد بضاعة').exists())


class ERPSetupDashboardTests(TestCase):
    def setUp(self):
        # Create users
        self.admin_user = User.objects.create_superuser(username='admin_test', password='password123')
        
        from django.contrib.auth.models import Group, Permission
        # Create all four system groups
        Group.objects.get_or_create(name='المدير العام')
        Group.objects.get_or_create(name='أمين المخزن')
        
        self.cashier_user = User.objects.create_user(username='cashier_test', password='password123')
        cashier_group, _ = Group.objects.get_or_create(name='الكاشير والمبيعات')
        add_invoice_perm = Permission.objects.get(codename='add_saleinvoice')
        cashier_group.permissions.add(add_invoice_perm)
        self.cashier_user.groups.add(cashier_group)

        self.tech_user = User.objects.create_user(username='tech_test', password='password123')
        tech_group, _ = Group.objects.get_or_create(name='فني الصيانة')
        change_ticket_perm = Permission.objects.get(codename='change_repairticket')
        tech_group.permissions.add(change_ticket_perm)
        self.tech_user.groups.add(tech_group)

    def test_setup_dashboard_access_control(self):
        """
        التحقق من صلاحيات الدخول لصفحة الإعدادات والتهيئة.
        """
        # 1. المسؤول العام يمتلك حق الدخول الكامل
        self.client.login(username='admin_test', password='password123')
        response = self.client.get('/setup/')
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # 2. الكاشير ليس لديه صلاحية ويتم توجيهه إلى POS
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get('/setup/')
        self.assertRedirects(response, '/pos/', fetch_redirect_response=False)
        self.client.logout()

        # 3. فني الصيانة ليس لديه صلاحية ويتم توجيهه إلى صفحة الصيانة
        self.client.login(username='tech_test', password='password123')
        response = self.client.get('/setup/')
        self.assertRedirects(response, '/repairs/', fetch_redirect_response=False)
        self.client.logout()

    def test_add_warehouse_via_setup_dashboard(self):
        """
        التحقق من إمكانية إضافة مخزن/فرع جديد بنجاح.
        """
        self.client.login(username='admin_test', password='password123')
        payload = {
            'action': 'add_warehouse',
            'name': 'مخزن النخبة التجريبي',
            'is_active': 'on'
        }
        response = self.client.post('/setup/', data=payload)
        self.assertRedirects(response, '/setup/')
        
        # التأكد من حفظ المخزن في قاعدة البيانات
        self.assertTrue(Warehouse.objects.filter(name='مخزن النخبة التجريبي', is_active=True).exists())

    def test_add_supplier_via_setup_dashboard(self):
        """
        التحقق من إمكانية إضافة مورد جديد بنجاح وتعيين contact_type بشكل تلقائي.
        """
        self.client.login(username='admin_test', password='password123')
        payload = {
            'action': 'add_supplier',
            'name': 'الشركة العالمية لقطع الغيار',
            'phone': '01234567890',
            'address': 'ش المنصورة الرئيسي'
        }
        response = self.client.post('/setup/', data=payload)
        self.assertRedirects(response, '/setup/')
        
        # التأكد من حفظ جهة الاتصال وتعيين نوعها كمورد
        supplier = Contact.objects.filter(name='الشركة العالمية لقطع الغيار').first()
        self.assertIsNotNone(supplier)
        self.assertEqual(supplier.contact_type, 'supplier')
        self.assertEqual(supplier.phone, '01234567890')

    def test_add_product_via_setup_dashboard_and_duplicate_prevention(self):
        """
        التحقق من إضافة صنف جديد بنجاح، ومنع تكرار الباركود.
        """
        self.client.login(username='admin_test', password='password123')
        
        # 1. إضافة صنف ناجحة
        payload = {
            'action': 'add_product',
            'name': 'شاحن أنكر 65 واط',
            'barcode_qr': 'ANKER65W',
            'product_type': 'accessory',
            'selling_price': '1200.00',
            'requires_imei': ''
        }
        response = self.client.post('/setup/', data=payload)
        self.assertRedirects(response, '/setup/')
        self.assertTrue(Product.objects.filter(barcode_qr='ANKER65W', name='شاحن أنكر 65 واط').exists())

        # 2. محاولة إضافة نفس الصنف بباركود مكرر
        payload_dup = {
            'action': 'add_product',
            'name': 'شاحن أنكر مكرر',
            'barcode_qr': 'ANKER65W',
            'product_type': 'accessory',
            'selling_price': '1500.00',
            'requires_imei': ''
        }
        response_dup = self.client.post('/setup/', data=payload_dup)
        self.assertEqual(response_dup.status_code, 200) # يرجع لنفس الصفحة ويعرض الخطأ
        # لم يتم إنشاء صنف ثانٍ بنفس الباركود
        self.assertEqual(Product.objects.filter(barcode_qr='ANKER65W').count(), 1)
        
        # التحقق من وجود رسالة التنبيه العامة بالخطأ في الرسائل
        messages = list(response_dup.context['messages'])
        self.assertTrue(len(messages) > 0)
        self.assertIn("خطأ في إدخال بيانات الصنف.", str(messages[0]))
        
        # التحقق من أن حقل الباركود يحتوي على خطأ تكرار الحقل من النموذج
        form = response_dup.context['product_form']
        self.assertFalse(form.is_valid())
        self.assertIn('barcode_qr', form.errors)

    def test_add_cashier_user_via_setup_dashboard(self):
        """
        التحقق من إمكانية إضافة مستخدم جديد (كاشير) بنجاح وإسناده للمجموعة الصحيحة.
        """
        self.client.login(username='admin_test', password='password123')
        payload = {
            'action': 'add_user',
            'username': 'new_cashier_user',
            'first_name': 'ممدوح',
            'last_name': 'أحمد',
            'email': 'mamdouh@easymb.com',
            'password': 'mamdouh_password',
            'role': 'الكاشير والمبيعات'
        }
        response = self.client.post('/setup/', data=payload)
        self.assertRedirects(response, '/setup/')

        # التحقق من قاعدة البيانات
        user = User.objects.filter(username='new_cashier_user').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'ممدوح')
        self.assertEqual(user.last_name, 'أحمد')
        self.assertEqual(user.email, 'mamdouh@easymb.com')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.groups.filter(name='الكاشير والمبيعات').exists())

    def test_add_general_manager_user_via_setup_dashboard(self):
        """
        التحقق من إضافة مستخدم بدور المدير العام وتأكيد منحه رتبة إداري (is_staff).
        """
        self.client.login(username='admin_test', password='password123')
        payload = {
            'action': 'add_user',
            'username': 'new_manager_user',
            'first_name': 'علي',
            'last_name': 'حسن',
            'email': 'ali@easymb.com',
            'password': 'ali_password',
            'role': 'المدير العام'
        }
        response = self.client.post('/setup/', data=payload)
        self.assertRedirects(response, '/setup/')

        # التحقق من قاعدة البيانات
        user = User.objects.filter(username='new_manager_user').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'علي')
        self.assertEqual(user.last_name, 'حسن')
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.groups.filter(name='المدير العام').exists())

    def test_add_user_duplicate_username(self):
        """
        التحقق من منع تسجيل اسم مستخدم مكرر وعرض خطأ التحقق.
        """
        self.client.login(username='admin_test', password='password123')
        # محاولة إضافة مستخدم باسم 'cashier_test' المسجل مسبقاً في setUp
        payload = {
            'action': 'add_user',
            'username': 'cashier_test',
            'first_name': 'تكرار',
            'last_name': 'مستخدم',
            'email': 'test@easymb.com',
            'password': 'password1234',
            'role': 'فني الصيانة'
        }
        response = self.client.post('/setup/', data=payload)
        self.assertEqual(response.status_code, 200)

        # التحقق من عدم تكراره ومن وجود أخطاء بالنموذج
        self.assertEqual(User.objects.filter(username='cashier_test').count(), 1)
        form = response.context['user_form']
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)



class ERPDetailsViewsTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        
        # Create Users
        self.admin = User.objects.create_superuser(username='admin_details', password='password123')
        self.staff_cashier = User.objects.create_user(username='cashier_details', password='password123', is_staff=True)
        
        # Assign permissions to cashier
        from django.contrib.auth.models import Permission
        view_sale = Permission.objects.get(codename='view_saleinvoice')
        view_purchase = Permission.objects.get(codename='view_purchaseinvoice')
        self.staff_cashier.user_permissions.add(view_sale, view_purchase)
        
        self.unprivileged_user = User.objects.create_user(username='user_no_perms', password='password123')
        
        # Create context models
        self.showroom = Warehouse.objects.create(name='المعرض الرئيسي', is_active=True)
        self.customer = Contact.objects.create(name='عميل التفاصيل', phone='01123456789', contact_type='customer')
        self.product = Product.objects.create(
            name='كابل شحن تجريبي',
            barcode_qr='CABLE123',
            product_type='accessory',
            average_cost=Decimal('30.00'),
            selling_price=Decimal('70.00'),
            requires_imei=False
        )
        
        # Create a CashShift and SaleInvoice
        self.shift = CashShift.objects.create(
            cashier=self.admin,
            start_time=timezone.now(),
            opening_balance=Decimal('1000.00'),
            status='open'
        )
            
        self.invoice = SaleInvoice.objects.create(
            shift=self.shift,
            cashier=self.admin,
            customer=self.customer,
            total_amount=Decimal('70.00'),
            discount=Decimal('0.00'),
            net_amount=Decimal('70.00')
        )
        self.sale_item = SaleItem.objects.create(
            invoice=self.invoice,
            product=self.product,
            warehouse=self.showroom,
            quantity=1,
            unit_price=Decimal('70.00')
        )
        
        # Create a RepairTicket
        self.ticket = RepairTicket.objects.create(
            customer=self.customer,
            technician=self.admin,
            device_model='iPhone 13',
            device_imei='123456789012345',
            issue_description='شاشة مكسورة',
            status='pending',
            estimated_cost=Decimal('500.00'),
            labor_cost=Decimal('200.00')
        )

        # Create a PurchaseInvoice
        self.supplier = Contact.objects.create(name='مورد تفاصيل', phone='01198765432', contact_type='supplier')
        self.purchase_invoice = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
            total_amount=Decimal('100.00'),
            net_amount=Decimal('100.00'),
            payment_method='cash',
            paid_amount=Decimal('100.00')
        )
        self.purchase_item = PurchaseItem.objects.create(
            invoice=self.purchase_invoice,
            product=self.product,
            warehouse=self.showroom,
            quantity=2,
            unit_cost=Decimal('50.00')
        )

    def test_sale_invoice_detail_view(self):
        # 1. Unauthenticated redirect
        response = self.client.get(f'/sales/{self.invoice.id}/')
        self.assertRedirects(response, f'/accounts/login/?next=/sales/{self.invoice.id}/')
        
        # 2. Authenticated but no permission (raises 403 PermissionDenied)
        self.client.login(username='user_no_perms', password='password123')
        response = self.client.get(f'/sales/{self.invoice.id}/')
        self.assertEqual(response.status_code, 403)
        
        # 3. Authenticated cashier with view permission
        self.client.login(username='cashier_details', password='password123')
        response = self.client.get(f'/sales/{self.invoice.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/sale_invoice_detail.html')
        self.assertEqual(response.context['invoice'].id, self.invoice.id)
        self.assertContains(response, 'عميل التفاصيل')
        self.assertContains(response, 'كابل شحن تجريبي')
        
        # 4. Superuser admin
        self.client.login(username='admin_details', password='password123')
        response = self.client.get(f'/sales/{self.invoice.id}/')
        self.assertEqual(response.status_code, 200)

    def test_repair_ticket_detail_view(self):
        # 1. Unauthenticated redirect
        response = self.client.get(f'/repairs/{self.ticket.id}/detail/')
        self.assertRedirects(response, f'/accounts/login/?next=/repairs/{self.ticket.id}/detail/')
        
        # 2. Authenticated but no permission (raises 403 PermissionDenied)
        self.client.login(username='user_no_perms', password='password123')
        response = self.client.get(f'/repairs/{self.ticket.id}/detail/')
        self.assertEqual(response.status_code, 403)
        
        # 3. Superuser admin
        self.client.login(username='admin_details', password='password123')
        response = self.client.get(f'/repairs/{self.ticket.id}/detail/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/repair_ticket_detail.html')
        self.assertEqual(response.context['ticket'].id, self.ticket.id)
        self.assertContains(response, 'iPhone 13')
        self.assertContains(response, 'شاشة مكسورة')

    def test_purchase_invoice_detail_view(self):
        """
        التحقق من تفاصيل فاتورة المشتريات (B2B) والتحكم بالصلاحيات.
        """
        # 1. Unauthenticated redirect
        response = self.client.get(f'/purchases/{self.purchase_invoice.id}/')
        self.assertRedirects(response, f'/accounts/login/?next=/purchases/{self.purchase_invoice.id}/')
        
        # 2. Authenticated but no permission (raises 403 PermissionDenied)
        self.client.login(username='user_no_perms', password='password123')
        response = self.client.get(f'/purchases/{self.purchase_invoice.id}/')
        self.assertEqual(response.status_code, 403)
        
        # 3. Authenticated cashier with view permission
        self.client.login(username='cashier_details', password='password123')
        response = self.client.get(f'/purchases/{self.purchase_invoice.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/purchase_invoice_detail.html')
        self.assertEqual(response.context['invoice'].id, self.purchase_invoice.id)
        self.assertContains(response, 'مورد تفاصيل')
        self.assertContains(response, 'كابل شحن تجريبي')
        
        # 4. Superuser admin
        self.client.login(username='admin_details', password='password123')
        response = self.client.get(f'/purchases/{self.purchase_invoice.id}/')
        self.assertEqual(response.status_code, 200)

    def test_purchase_invoice_pay_view(self):
        """
        التحقق من عمل عرض سداد فاتورة المشتريات (purchase_pay).
        """
        from decimal import Decimal
        from django.utils import timezone
        from erp.models import PurchaseInvoice, CashShift, Expense
        
        # 1. إنشاء فاتورة مشتريات آجلة بالكامل
        credit_invoice = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
            total_amount=Decimal('500.00'),
            net_amount=Decimal('500.00'),
            payment_method='credit',
            paid_amount=Decimal('0.00')
        )
        self.assertEqual(credit_invoice.remaining_amount, Decimal('500.00'))
        
        # 2. مستخدم بدون صلاحية تعديل فواتير الشراء
        self.client.login(username='user_no_perms', password='password123')
        response = self.client.post(f'/purchases/{credit_invoice.id}/pay/', {'amount': '100.00'})
        self.assertEqual(response.status_code, 403) # Forbidden
        
        # 3. مستخدم بصلاحية (أدمن) يسدد دفعة بدون خصم من الوردية
        self.client.login(username='admin_details', password='password123')
        response = self.client.post(f'/purchases/{credit_invoice.id}/pay/', {
            'amount': '150.00',
            'deduct_from_shift': 'off'
        })
        self.assertEqual(response.status_code, 302) # Redirect
        
        # تحقق من تعديل الفاتورة
        credit_invoice.refresh_from_db()
        self.assertEqual(credit_invoice.paid_amount, Decimal('150.00'))
        self.assertEqual(credit_invoice.remaining_amount, Decimal('350.00'))
        
        # تحقق من عدم إضافة أي مصروفات
        self.assertEqual(Expense.objects.filter(description__icontains=str(credit_invoice.id)).count(), 0)
        
        # 4. سداد مع الخصم من الوردية
        # تعيين صلاحية تعديل فواتير الشراء للمستخدم الكاشير
        from django.contrib.auth.models import Permission
        change_invoice_perm = Permission.objects.get(codename='change_purchaseinvoice')
        view_shift_perm = Permission.objects.get(codename='view_cashshift')
        self.staff_cashier.user_permissions.add(change_invoice_perm, view_shift_perm)
        
        # تسجيل الدخول بالكاشير
        self.client.login(username='cashier_details', password='password123')
        
        # فتح وردية للكاشير
        shift = CashShift.objects.create(
            cashier=self.staff_cashier,
            start_time=timezone.now(),
            opening_balance=Decimal('500.00'),
            status='open'
        )
        
        response = self.client.post(f'/purchases/{credit_invoice.id}/pay/', {
            'amount': '100.00',
            'deduct_from_shift': 'on'
        })
        self.assertEqual(response.status_code, 302)
        
        # تحقق من تحديث الفاتورة
        credit_invoice.refresh_from_db()
        self.assertEqual(credit_invoice.paid_amount, Decimal('250.00')) # 150 + 100
        
        # تحقق من إنشاء المصروف للوردية
        expense = Expense.objects.filter(shift=shift).first()
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount, Decimal('100.00'))
        self.assertEqual(expense.category.name, "سداد موردين")

        # 5. محاولة السداد بمبلغ أكبر من المتوفر بالوردية (الوردية المتبقي بها هو 400 ج.م)
        response = self.client.post(f'/purchases/{credit_invoice.id}/pay/', {
            'amount': '450.00',
            'deduct_from_shift': 'on'
        })
        self.assertEqual(response.status_code, 302)
        # تحقق من عدم تغيير قيمة الفاتورة
        credit_invoice.refresh_from_db()
        self.assertEqual(credit_invoice.paid_amount, Decimal('250.00'))

    def test_shift_add_expense_insufficient_cash(self):
        """
        التحقق من رفض إضافة مصروفات تشغيلية بقيمة أكبر من النقدية المتاحة بالوردية.
        """
        from decimal import Decimal
        from erp.models import CashShift, ExpenseCategory
        
        # 1. إنشاء مستخدم مسؤول ووردية برصيد 100
        admin_user = User.objects.create_user(username='admin_exp_test', password='password123', is_staff=True, is_superuser=True)
        self.client.login(username='admin_exp_test', password='password123')
        
        shift = CashShift.objects.create(cashier=admin_user, opening_balance=Decimal('100.00'), status='open')
        category = ExpenseCategory.objects.create(name='مصاريف صيانة')
        
        # 2. محاولة إضافة مصروف أكبر من رصيد الوردية (150 ج.م)
        response = self.client.post('/shifts/add-expense/', {
            'category': category.id,
            'amount': '150.00',
            'description': 'أدوات'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('عذراً، لا يمكن تسجيل مصروف', response.json()['error'])
        
        # 3. محاولة إضافة مصروف مساوٍ للرصيد المتاح (100 ج.م)
        response_ok = self.client.post('/shifts/add-expense/', {
            'category': category.id,
            'amount': '100.00',
            'description': 'أدوات مقبولة'
        })
        self.assertEqual(response_ok.status_code, 200)
        
        # تحقق من تحديث الوردية
        shift.refresh_from_db()
        self.assertEqual(shift.expected_closing_balance, Decimal('0.00'))


class ERPInventoryDashboardTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        
        # Create Users
        self.admin = User.objects.create_superuser(username='admin_inv', password='password123')
        self.staff_cashier = User.objects.create_user(username='cashier_inv', password='password123', is_staff=True)
        
        # Assign permission view_stock to cashier
        from django.contrib.auth.models import Permission
        view_stock = Permission.objects.get(codename='view_stock')
        self.staff_cashier.user_permissions.add(view_stock)
        
        self.unprivileged_user = User.objects.create_user(username='user_no_inv_perms', password='password123')
        
        # Create Warehouses
        self.showroom = Warehouse.objects.create(name='المعرض التجريبي', is_active=True)
        self.main_wh = Warehouse.objects.create(name='المستودع الاحتياطي', is_active=True)
        
        # Create Products
        self.bulk_item = Product.objects.create(
            name='لاصقة حماية شاشة',
            barcode_qr='GLASS789',
            product_type='accessory',
            average_cost=Decimal('15.00'),
            selling_price=Decimal('50.00'),
            requires_imei=False
        )
        self.phone_prod = Product.objects.create(
            name='iPhone 14 Pro',
            barcode_qr='IP14PRO',
            product_type='phone',
            average_cost=Decimal('40000.00'),
            selling_price=Decimal('45000.00'),
            requires_imei=True
        )
        
        # Seed Stock
        self.stock_showroom = Stock.objects.create(product=self.bulk_item, warehouse=self.showroom, quantity=20)
        self.stock_main = Stock.objects.create(product=self.bulk_item, warehouse=self.main_wh, quantity=50)
        
        # Seed Device in stock (available)
        self.device_available = Device.objects.create(
            product=self.phone_prod,
            imei='987654321098765',
            condition='new',
            warehouse=self.showroom,
            is_sold=False,
            cost=Decimal('39000.00')
        )
        
        # Seed Device sold (should not be in inventory dashboard)
        self.device_sold = Device.objects.create(
            product=self.phone_prod,
            imei='111222333444555',
            condition='new',
            warehouse=self.showroom,
            is_sold=True,
            cost=Decimal('39000.00')
        )

    def test_inventory_dashboard_access_control(self):
        # 1. Unauthenticated redirect
        response = self.client.get('/inventory/')
        self.assertRedirects(response, '/accounts/login/?next=/inventory/')
        
        # 2. Authenticated but no permission
        self.client.login(username='user_no_inv_perms', password='password123')
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 403)
        
        # 3. Authenticated with view_stock permission
        self.client.login(username='cashier_inv', password='password123')
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/inventory.html')

    def test_inventory_dashboard_data_and_calculations(self):
        self.client.login(username='admin_inv', password='password123')
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        
        # Check counts
        self.assertEqual(response.context['total_bulk_qty'], 70) # 20 + 50
        self.assertEqual(response.context['total_devices_qty'], 1) # only device_available
        
        # Check valuation calculations:
        # Total cost: 70 * 15.00 (average cost) + 39000.00 (device cost) = 1050 + 39000 = 40050.00
        self.assertEqual(response.context['total_cost_valuation'], Decimal('40050.00'))
        # Total selling: 70 * 50.00 + 45000.00 = 3500 + 45000 = 48500.00
        self.assertEqual(response.context['total_selling_valuation'], Decimal('48500.00'))

    def test_inventory_dashboard_filtering(self):
        self.client.login(username='admin_inv', password='password123')
        
        # Filter by showroom warehouse
        response = self.client.get(f'/inventory/?warehouse={self.showroom.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['bulk_stock']), 1)
        self.assertEqual(response.context['bulk_stock'][0].quantity, 20)
        self.assertEqual(len(response.context['devices']), 1)
        
        # Filter by main warehouse
        response = self.client.get(f'/inventory/?warehouse={self.main_wh.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['bulk_stock']), 1)
        self.assertEqual(response.context['bulk_stock'][0].quantity, 50)
        self.assertEqual(len(response.context['devices']), 0)
        
        # Filter by search term q (matches the product across both warehouses)
        response = self.client.get('/inventory/?q=GLASS789')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['bulk_stock']), 2)
        self.assertEqual(len(response.context['devices']), 0)


class ERPStockTransferViewTests(TestCase):
    def setUp(self):
        # Create superuser to bypass permission checks
        self.user = User.objects.create_superuser(username='admin_transfer', password='password123')
        
        # Create Warehouses
        self.wh_from = Warehouse.objects.create(name='ظ…ط®ط²ظ† ط§ظ„ظ…طµط¯ط±', is_active=True)
        self.wh_to = Warehouse.objects.create(name='ظ…ط®ط²ظ† ط§ظ„ظˆط¬ظ‡ط©', is_active=True)
        
        # Create Products
        self.bulk_product = Product.objects.create(
            name='ط¬ط±ط§ط¨ ط³ظٹظ„ظٹظƒظˆظ†',
            barcode_qr='BULK_TEST_123',
            product_type='accessory',
            average_cost=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            requires_imei=False
        )
        self.phone_product = Product.objects.create(
            name='ط¢ظٹظپظˆظ† 15',
            barcode_qr='PHONE_TEST_123',
            product_type='phone',
            average_cost=Decimal('40000.00'),
            selling_price=Decimal('45000.00'),
            requires_imei=True
        )
        
        # Create Stock for bulk product in wh_from
        Stock.objects.create(product=self.bulk_product, warehouse=self.wh_from, quantity=15)
        
        # Create Device for phone product in wh_from
        self.device = Device.objects.create(
            product=self.phone_product,
            imei='IMEI_TRANSFER_TEST',
            condition='new',
            warehouse=self.wh_from,
            is_sold=False,
            cost=Decimal('40000.00')
        )
        
    def test_transfer_create_view_get_context(self):
        self.client.login(username='admin_transfer', password='password123')
        response = self.client.get('/transfers/create/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/transfer_create.html')
        
        # Verify warehouse_stock_json contains correct information
        import json
        stock_data = json.loads(response.context['warehouse_stock_json'])
        
        # wh_from must contain the products and devices
        wh_from_id = str(self.wh_from.id)
        self.assertIn(wh_from_id, stock_data)
        
        wh_from_products = stock_data[wh_from_id]['products']
        product_ids = [p['id'] for p in wh_from_products]
        
        # bulk_product has stock, so it must be present
        self.assertIn(self.bulk_product.id, product_ids)
        # phone_product has device, so it must be present
        self.assertIn(self.phone_product.id, product_ids)
        
        # Verify device details
        phone_devices = stock_data[wh_from_id]['devices'][str(self.phone_product.id)]
        self.assertEqual(len(phone_devices), 1)
        self.assertEqual(phone_devices[0]['id'], self.device.id)
        self.assertIn('IMEI_TRANSFER_TEST', phone_devices[0]['display'])
        
        # wh_to must have empty stock
        wh_to_id = str(self.wh_to.id)
        self.assertIn(wh_to_id, stock_data)
        self.assertEqual(len(stock_data[wh_to_id]['products']), 0)
        self.assertEqual(len(stock_data[wh_to_id]['devices']), 0)

    def test_transfer_create_view_post_success(self):
        self.client.login(username='admin_transfer', password='password123')
        
        # Post data to create a transfer order
        post_data = {
            'from_warehouse': self.wh_from.id,
            'to_warehouse': self.wh_to.id,
            'status': 'pending',
            'items-TOTAL_FORMS': '2',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            
            # Row 0: bulk product
            'items-0-product': self.bulk_product.id,
            'items-0-device': '',
            'items-0-quantity': '5',
            
            # Row 1: phone product
            'items-1-product': self.phone_product.id,
            'items-1-device': self.device.id,
            'items-1-quantity': '1',
        }
        
        response = self.client.post('/transfers/create/', post_data)
        self.assertRedirects(response, '/transfers/')
        
        # Check database instances
        transfers = StockTransfer.objects.filter(from_warehouse=self.wh_from)
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        self.assertEqual(transfer.from_warehouse, self.wh_from)
        self.assertEqual(transfer.to_warehouse, self.wh_to)
        
        items = transfer.items.all()
        self.assertEqual(items.count(), 2)
        
        bulk_item = items.get(product=self.bulk_product)
        self.assertEqual(bulk_item.quantity, 5)
        self.assertIsNone(bulk_item.device)
        
        phone_item = items.get(product=self.phone_product)
        self.assertEqual(phone_item.quantity, 1)
        self.assertEqual(phone_item.device, self.device)


class ERPReportsViewTests(TestCase):
    def setUp(self):
        # 1. Create Users
        self.admin = User.objects.create_superuser(username='admin_rep', password='password123')
        self.cashier = User.objects.create_user(username='cashier_rep', password='password123')
        
        # 2. Create Warehouse
        self.wh = Warehouse.objects.create(name='مستودع التقارير', is_active=True)
        
        # 3. Create Contacts
        self.supplier = Contact.objects.create(name='المورد الممتاز', phone='01111111111', contact_type='supplier')
        self.customer = Contact.objects.create(name='العميل المحترم', phone='01222222222', contact_type='customer')
        
        # 4. Create Products
        self.bulk_prod = Product.objects.create(
            name='سماعة بلوتوث',
            barcode_qr='ACC_REP_1',
            product_type='accessory',
            average_cost=Decimal('200.00'),
            selling_price=Decimal('350.00'),
            requires_imei=False
        )
        self.phone_prod = Product.objects.create(
            name='آيفون 15 برو',
            barcode_qr='PHONE_REP_1',
            product_type='phone',
            average_cost=Decimal('45000.00'),
            selling_price=Decimal('50000.00'),
            requires_imei=True
        )
        
        # Stock setup
        Stock.objects.create(product=self.bulk_prod, warehouse=self.wh, quantity=20)
        self.dev = Device.objects.create(
            product=self.phone_prod,
            imei='IMEI_REP_123',
            condition='new',
            warehouse=self.wh,
            is_sold=False,
            cost=Decimal('45000.00')
        )
        
        # Create a CashShift (required for SalesInvoices and Expenses)
        self.shift = CashShift.objects.create(
            cashier=self.admin,
            opening_balance=Decimal('1000.00'),
            status='open'
        )
        
        # 5. Create Transactions
        # A. Purchase Invoice: Total 5000, Paid 2000 -> Remaining 3000
        purchase = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
            total_amount=Decimal('5000.00'),
            discount=Decimal('0.00'),
            deduction_addition_tax=Decimal('0.00'),
            net_amount=Decimal('5000.00'),
            payment_method='partial',
            paid_amount=Decimal('2000.00')
        )
        PurchaseItem.objects.create(
            invoice=purchase,
            product=self.bulk_prod,
            warehouse=self.wh,
            quantity=25,
            unit_cost=Decimal('200.00')
        )
        
        # B. Sale Invoice: Net 8000
        sale = SaleInvoice.objects.create(
            shift=self.shift,
            customer=self.customer,
            cashier=self.admin,
            total_amount=Decimal('8000.00'),
            discount=Decimal('0.00'),
            net_amount=Decimal('8000.00')
        )
        SaleItem.objects.create(
            invoice=sale,
            product=self.bulk_prod,
            warehouse=self.wh,
            quantity=10,
            unit_price=Decimal('350.00')
        )
        Payment.objects.create(
            invoice=sale,
            amount=Decimal('8000.00'),
            payment_method='cash'
        )
        
        # C. Repair Ticket
        self.ticket = RepairTicket.objects.create(
            customer=self.customer,
            technician=self.admin,
            device_model='آيفون 15 برو',
            device_imei='IMEI_REP_123',
            issue_description='شاشة مكسورة',
            labor_cost=Decimal('500.00'),
            status='delivered'
        )
        
        # D. Expense
        self.cat = ExpenseCategory.objects.create(name='شاي وقهوة')
        Expense.objects.create(
            shift=self.shift,
            category=self.cat,
            amount=Decimal('150.00'),
            description='ضيافة'
        )
        
    def test_reports_dashboard_access_control(self):
        # 1. Anonymous user redirected to login
        response = self.client.get('/reports/')
        self.assertRedirects(response, '/accounts/login/?next=/reports/')
        
        # 2. Cashier user gets 403 Forbidden
        self.client.login(username='cashier_rep', password='password123')
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'erp/403.html')
        
        # 3. Admin user gets 200 OK
        self.client.login(username='admin_rep', password='password123')
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'erp/reports.html')
        
    def test_reports_dashboard_calculations(self):
        self.client.login(username='admin_rep', password='password123')
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        
        # 1. Verify Financials
        financials = response.context['financials']
        # Sales Net Revenue = 8000
        self.assertEqual(financials['total_sales_revenue'], Decimal('8000.00'))
        # COGS = 10 (quantity) * 200 (average cost) = 2000
        self.assertEqual(financials['total_cogs'], Decimal('2000.00'))
        # Expenses = 150
        self.assertEqual(financials['total_expenses'], Decimal('150.00'))
        # Profit = 8000 - 2000 - 150 = 5850
        self.assertEqual(financials['net_profit'], Decimal('5850.00'))
        
        # 2. Verify Supplier outstanding statements
        statements = financials['supplier_statements']
        self.assertEqual(len(statements), 1)
        self.assertEqual(statements[0]['supplier'], self.supplier)
        self.assertEqual(statements[0]['total_purchased'], Decimal('5000.00'))
        self.assertEqual(statements[0]['total_paid'], Decimal('2000.00'))
        self.assertEqual(statements[0]['remaining'], Decimal('3000.00'))
        
        # 3. Verify Purchases summary
        purchases = response.context['purchases']
        self.assertEqual(purchases['count'], 1)
        self.assertEqual(purchases['total_net'], Decimal('5000.00'))
        self.assertEqual(purchases['total_paid'], Decimal('2000.00'))
        self.assertEqual(purchases['total_remaining'], Decimal('3000.00'))
        
        # 4. Verify Sales summary
        sales = response.context['sales']
        self.assertEqual(sales['count'], 1)
        self.assertEqual(sales['net'], Decimal('8000.00'))
        self.assertEqual(sales['payment_breakdown']['cash'], Decimal('8000.00'))
        
        # 5. Verify Maintenance summary
        maintenance = response.context['maintenance']
        self.assertEqual(maintenance['count'], 1)
        self.assertEqual(maintenance['status_breakdown']['delivered'], 1)

    def test_reports_dashboard_interactive_details(self):
        self.client.login(username='admin_rep', password='password123')
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        
        # Verify new context lists
        financials = response.context['financials']
        self.assertIn('sales_list', financials)
        self.assertIn('cogs_list', financials)
        self.assertIn('expenses_all', financials)
        
        # Verify supplier statements contain invoices list
        supplier_statement = financials['supplier_statements'][0]
        self.assertIn('invoices', supplier_statement)
        self.assertEqual(len(supplier_statement['invoices']), 1)
        self.assertEqual(supplier_statement['invoices'][0].net_amount, Decimal('5000.00'))
        
        # Verify sales list has 1 invoice
        self.assertEqual(len(financials['sales_list']), 1)
        self.assertEqual(financials['sales_list'][0].net_amount, Decimal('8000.00'))
        
        # Verify cogs list has 1 item
        self.assertEqual(len(financials['cogs_list']), 1)
        self.assertEqual(financials['cogs_list'][0]['total_cost'], Decimal('2000.00'))
        
        # Verify purchases list has 1 invoice
        purchases = response.context['purchases']
        self.assertIn('purchases_list', purchases)
        self.assertEqual(len(purchases['purchases_list']), 1)
        self.assertEqual(purchases['purchases_list'][0].net_amount, Decimal('5000.00'))
        
        # Create a spare part product and some stock to test accessories and spare parts counts
        spare_part = Product.objects.create(
            name='شاشة آيفون 15',
            barcode_qr='PART_REP_1',
            product_type='spare_part',
            average_cost=Decimal('500.00'),
            selling_price=Decimal('800.00'),
            requires_imei=False
        )
        Stock.objects.create(product=spare_part, warehouse=self.wh, quantity=15)
        
        # Re-fetch page to include new spare part
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        
        from django.db.models import Sum
        inventory = response.context['inventory']
        expected_accessories = Stock.objects.filter(product__product_type='accessory', quantity__gt=0).aggregate(total=Sum('quantity'))['total'] or 0
        expected_spare_parts = Stock.objects.filter(product__product_type='spare_part', quantity__gt=0).aggregate(total=Sum('quantity'))['total'] or 0
        self.assertEqual(inventory['accessories_count'], expected_accessories)
        self.assertEqual(inventory['spare_parts_count'], expected_spare_parts)
        self.assertEqual(len(inventory['accessories_stock']), Stock.objects.filter(product__product_type='accessory', quantity__gt=0).count())
        self.assertEqual(len(inventory['spare_parts_stock']), Stock.objects.filter(product__product_type='spare_part', quantity__gt=0).count())
        
        # Verify paginated products catalog in reports
        self.assertIn('products_page', inventory)
        self.assertGreater(len(inventory['products_page']), 0)
        
        # Test searching by name
        response_search_name = self.client.get('/reports/', {'inv_search': 'شاشة'})
        self.assertEqual(response_search_name.status_code, 200)
        search_inventory = response_search_name.context['inventory']
        self.assertEqual(len(search_inventory['products_page']), 1)
        self.assertEqual(search_inventory['products_page'][0].name, 'شاشة آيفون 15')
        
        # Test searching by barcode
        response_search_barcode = self.client.get('/reports/', {'inv_search': 'PART_REP_1'})
        self.assertEqual(response_search_barcode.status_code, 200)
        barcode_inventory = response_search_barcode.context['inventory']
        self.assertEqual(len(barcode_inventory['products_page']), 1)
        self.assertEqual(barcode_inventory['products_page'][0].barcode_qr, 'PART_REP_1')
        
        # Test HTMX request for inventory table
        response_htmx = self.client.get('/reports/', {'inv_search': 'شاشة'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='inventory-products-table-container')
        self.assertEqual(response_htmx.status_code, 200)
        self.assertTemplateUsed(response_htmx, 'erp/includes/reports_inventory_table.html')
        self.assertTemplateNotUsed(response_htmx, 'erp/reports.html')
        
        # Verify maintenance tickets page
        maintenance = response.context['maintenance']
        self.assertIn('tickets_page', maintenance)
        self.assertEqual(len(maintenance['tickets_page']), 1)
        self.assertEqual(maintenance['tickets_page'][0], self.ticket)
        
        # Test searching maintenance by customer name
        response_maint_search = self.client.get('/reports/', {'maint_search': 'العميل المحترم'})
        self.assertEqual(response_maint_search.status_code, 200)
        maint_context = response_maint_search.context['maintenance']
        self.assertEqual(len(maint_context['tickets_page']), 1)
        
        # Test HTMX request for maintenance table
        response_maint_htmx = self.client.get('/reports/', {'maint_search': 'العميل'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='maintenance-tickets-table-container')
        self.assertEqual(response_maint_htmx.status_code, 200)
        self.assertTemplateUsed(response_maint_htmx, 'erp/includes/reports_maintenance_table.html')
        self.assertTemplateNotUsed(response_maint_htmx, 'erp/reports.html')

    def test_reports_dashboard_maintenance_profits(self):
        self.client.login(username='admin_rep', password='password123')
        
        # 1. Create a spare part product
        spare_part = Product.objects.create(
            name="شاشة آيفون 15 برو",
            barcode_qr="SP-IPH15-SCR",
            product_type="spare_part",
            average_cost=Decimal("150.00"),
            selling_price=Decimal("250.00")
        )
        # Create stock
        Stock.objects.create(product=spare_part, warehouse=self.wh, quantity=5)
        
        # 2. Create another ticket with parts used
        ticket2 = RepairTicket.objects.create(
            customer=self.customer,
            technician=self.admin,
            device_model='آيفون 15 برو',
            device_imei='IMEI_REP_456',
            issue_description='شاشة تالفة',
            labor_cost=Decimal('300.00'),
            status='done'
        )
        # Consume spare part
        RepairPartUsed.objects.create(
            ticket=ticket2,
            product=spare_part,
            warehouse=self.wh,
            quantity=2,
            price=Decimal("250.00") # selling price
        )
        
        response = self.client.get('/reports/')
        self.assertEqual(response.status_code, 200)
        
        maintenance = response.context['maintenance']
        # We now have self.ticket (labor: 500, parts_profit: 0)
        # and ticket2 (labor: 300, parts_profit: (250-150)*2 = 200)
        # Total tickets = 2
        self.assertEqual(maintenance['count'], 2)
        # Total labor = 500 + 300 = 800
        self.assertEqual(maintenance['total_labor'], Decimal('800.00'))
        # Total parts profit = 200
        self.assertEqual(maintenance['parts_profit'], Decimal('200.00'))
        # Total maintenance profit = 800 + 200 = 1000
        self.assertEqual(maintenance['total_profit'], Decimal('1000.00'))
        
        # Verify tickets_list contains both tickets
        tickets_list = list(maintenance['tickets_list'])
        self.assertEqual(len(tickets_list), 2)
        
        # Test date filtering: if we filter for a range in the future, count should be 0
        from datetime import date, timedelta
        future_start = (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')
        future_end = (date.today() + timedelta(days=10)).strftime('%Y-%m-%d')
        
        response_filtered = self.client.get(f'/reports/?start_date={future_start}&end_date={future_end}')
        self.assertEqual(response_filtered.status_code, 200)
        maint_filtered = response_filtered.context['maintenance']
        self.assertEqual(maint_filtered['count'], 0)
        self.assertEqual(maint_filtered['total_profit'], Decimal('0.00'))

    def test_repair_ticket_notification_scheduling(self):
        self.client.login(username='admin_rep', password='password123')
        
        # Enable notifications for 'done' status in NotificationSettings
        from erp.models import NotificationSettings
        settings_obj = NotificationSettings.get_settings()
        settings_obj.whatsapp_enabled = True
        settings_obj.sender_phone = "01000000000"
        settings_obj.msg_done_enabled = True
        settings_obj.msg_done = "تم تعديل حالة تذكرتك #{ticket_id} إلى {status_display}"
        settings_obj.save()
        
        from erp.models import NotificationLog
        NotificationLog.objects.all().delete()
        
        # Verify that changing status enqueues a task
        response = self.client.post(f'/repairs/{self.ticket.id}/change-status/', {
            'status': 'done'
        })
        self.assertEqual(response.status_code, 200)
        
        # Verify a NotificationLog was created
        self.assertEqual(NotificationLog.objects.count(), 1)
        log = NotificationLog.objects.first()
        self.assertEqual(log.status, 'queued')
        self.assertIn(str(self.ticket.id), log.message_body)
        
        # Test executing the task manually with selenium mocked to verify task logic
        from erp.tasks import send_whatsapp_notification
        from unittest.mock import patch
        with patch('erp.tasks._send_via_whatsapp_web') as mock_send:
            send_whatsapp_notification(log.id)
            mock_send.assert_called_once()
            
        log.refresh_from_db()
        self.assertEqual(log.status, 'sent')


class ERPValidationTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from erp.models import Contact, Warehouse, Product, PurchaseInvoice
        User = get_user_model()
        self.user = User.objects.create_user(username='admin_val', password='password123')
        self.supplier = Contact.objects.create(name="مورد تجربة", phone="01010101010", contact_type='supplier')
        self.warehouse = Warehouse.objects.create(name="مخزن تجربة")
        self.product_serialized = Product.objects.create(
            name="آيفون تجربة",
            barcode_qr="11223344",
            product_type='phone',
            selling_price=Decimal('10000.00'),
            requires_imei=True
        )
        self.product_normal = Product.objects.create(
            name="جراب تجربة",
            barcode_qr="55667788",
            product_type='accessory',
            selling_price=Decimal('100.00'),
            requires_imei=False
        )
        self.invoice = PurchaseInvoice.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            total_amount=Decimal('0.00'),
            net_amount=Decimal('0.00'),
            payment_method='credit'
        )

    def test_purchase_item_form_validation(self):
        """
        التحقق من صحة مدخلات النموذج لبند شراء يحتوي على جهاز مسيرن.
        """
        from erp.forms import PurchaseItemForm
        # 1. حالة منتج مسيرن وبدون سيريالات (فشل)
        form_data = {
            'product': self.product_serialized.id,
            'warehouse': self.warehouse.id,
            'quantity': 2,
            'unit_cost': Decimal('8000.00'),
            'imei_list': ''
        }
        form = PurchaseItemForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("يتطلب إدخال سيريالات", form.errors['__all__'][0])

        # 2. حالة منتج مسيرن والكمية لا تطابق عدد السيريالات (فشل)
        form_data['imei_list'] = '111111111111111'  # سيريال واحد والكمية 2
        form = PurchaseItemForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("لا يتطابق مع الكمية المحددة", form.errors['__all__'][0])

        # 3. حالة منتج مسيرن ببيانات صحيحة (نجاح)
        form_data['imei_list'] = '111111111111111, 222222222222222'
        form = PurchaseItemForm(data=form_data)
        self.assertTrue(form.is_valid())

        # 4. حالة منتج عادي بدون سيريالات (نجاح)
        form_data_normal = {
            'product': self.product_normal.id,
            'warehouse': self.warehouse.id,
            'quantity': 10,
            'unit_cost': Decimal('50.00'),
            'imei_list': ''
        }
        form = PurchaseItemForm(data=form_data_normal)
        self.assertTrue(form.is_valid())

    def test_purchase_item_model_clean_validation(self):
        """
        التحقق من عمل التحقق على مستوى الموديل (PurchaseItem.clean).
        """
        from django.core.exceptions import ValidationError
        from erp.models import PurchaseItem

        # 1. بدون سيريالات
        item1 = PurchaseItem(
            invoice=self.invoice,
            product=self.product_serialized,
            warehouse=self.warehouse,
            quantity=2,
            unit_cost=Decimal('8000.00'),
            imei_list=''
        )
        with self.assertRaises(ValidationError):
            item1.full_clean()

        # 2. كمية غير متطابقة
        item2 = PurchaseItem(
            invoice=self.invoice,
            product=self.product_serialized,
            warehouse=self.warehouse,
            quantity=2,
            unit_cost=Decimal('8000.00'),
            imei_list='111111111111111'
        )
        with self.assertRaises(ValidationError):
            item2.full_clean()

        # 3. بيانات صحيحة
        item3 = PurchaseItem(
            invoice=self.invoice,
            product=self.product_serialized,
            warehouse=self.warehouse,
            quantity=2,
            unit_cost=Decimal('8000.00'),
            imei_list='111111111111111, 222222222222222'
        )
        item3.full_clean()  # لا يرفع أي استثناء

    def test_pos_inventory_snapshot_view(self):
        """
        التحقق من أن عرض pos_inventory_snapshot يرجع البيانات بصيغة JSON وبحالة 200.
        """
        self.client.login(username='admin_val', password='password123')
        response = self.client.get('/pos/inventory-snapshot/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('devices', data)
        self.assertIn('stocks', data)


