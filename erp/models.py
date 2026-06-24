# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.core.validators import RegexValidator

# ==========================================
# Validators
# ==========================================
phone_validator = RegexValidator(
    regex=r'^\d{11}$',
    message="رقم الهاتف يجب أن يتكون من 11 رقماً فقط."
)

national_id_validator = RegexValidator(
    regex=r'^\d{14}$',
    message="الرقم القومي يجب أن يتكون من 14 رقماً فقط."
)

# ==========================================
# 1. إعدادات المحل والهوية البصرية (Settings)
# ==========================================
class StoreSetting(models.Model):
    store_name = models.CharField(max_length=255, verbose_name="اسم المحل")
    logo = models.ImageField(upload_to='store_assets/', null=True, blank=True, verbose_name="شعار المحل")
    receipt_header = models.TextField(blank=True, verbose_name="ترويسة الفاتورة")
    receipt_footer = models.TextField(blank=True, verbose_name="تذييل الفاتورة")
    whatsapp_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="مفتاح API الواتساب")
    sms_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="مفتاح API الرسائل النصية")
    
    # إعدادات البصمة الجغرافية (Geolocation)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="خط العرض (Latitude) للمحل")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="خط الطول (Longitude) للمحل")
    allowed_radius = models.IntegerField(default=50, verbose_name="النطاق المسموح للبصمة (بالمتر)")

    class Meta:
        verbose_name = "إعدادات المتجر"
        verbose_name_plural = "إعدادات المتجر"

    def __str__(self):
        return self.store_name

# ==========================================
# 2. جهات الاتصال (Contacts)
# ==========================================
class Contact(models.Model):
    CONTACT_TYPES = (
        ('customer', 'عميل'),
        ('supplier', 'مورد شركات'),
        ('used_seller', 'بائع أجهزة مستعملة (فرد)'),
    )
    name = models.CharField(max_length=255, verbose_name="الاسم")
    phone = models.CharField(max_length=20, unique=True, validators=[phone_validator], verbose_name="رقم الهاتف")
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPES, verbose_name="نوع جهة الاتصال")
    
    # بيانات قانونية لبائعي الأجهزة المستعملة
    national_id = models.CharField(max_length=14, blank=True, null=True, validators=[national_id_validator], verbose_name="الرقم القومي")
    address = models.TextField(blank=True, null=True, verbose_name="العنوان")
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="رصيد أول المدة")

    @property
    def current_balance(self):
        balance = self.opening_balance
        if self.contact_type in ['customer', 'used_seller']:
            # الديون المستحقة على العميل
            unpaid_sales = self.saleinvoice_set.filter(payment_method__in=['credit', 'partial'])
            balance += sum(inv.remaining_amount for inv in unpaid_sales)
            # خصم المبالغ المسددة (سندات القبض)
            receipts = self.contacttransaction_set.filter(transaction_type='receipt')
            balance -= sum(t.amount for t in receipts)
        elif self.contact_type == 'supplier':
            # المستحقات للمورد
            unpaid_purchases = self.purchaseinvoice_set.filter(payment_method__in=['credit', 'partial'])
            balance += sum(inv.remaining_amount for inv in unpaid_purchases)
            # خصم المبالغ المدفوعة (سندات الصرف)
            payments = self.contacttransaction_set.filter(transaction_type='payment')
            balance -= sum(t.amount for t in payments)
        return balance

    class Meta:
        verbose_name = "جهة اتصال"
        verbose_name_plural = "جهات الاتصال"

    def __str__(self):
        return f"{self.name} - {self.get_contact_type_display()}"

class ContactTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('receipt', 'سند قبض (استلام نقدية)'),
        ('payment', 'سند صرف (دفع نقدية)')
    )
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="جهة الاتصال")
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, verbose_name="الخزينة")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="نوع الحركة")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="البيان")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ")
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="المستخدم")

    class Meta:
        verbose_name = "حركة حساب"
        verbose_name_plural = "حركات الحسابات"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            if self.transaction_type == 'receipt':
                self.treasury.balance += self.amount
            elif self.transaction_type == 'payment':
                self.treasury.balance -= self.amount
            self.treasury.save()

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.contact.name} - {self.amount}"

# ==========================================
# 3. المخازن والأصناف (Inventory & Products)
# ==========================================
class Warehouse(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم المخزن / الفرع")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "مخزن / فرع"
        verbose_name_plural = "المخازن والفروع"

    def __str__(self):
        return self.name

class Product(models.Model):
    PRODUCT_TYPES = (
        ('phone', 'موبايل'),
        ('accessory', 'إكسسوار عام'),
        ('cover_screen', 'جراب + اسكرينة'),
        ('electrical', 'كهرباء'),
        ('spare_part', 'قطعة غيار'),
    )
    name = models.CharField(max_length=255, verbose_name="اسم الصنف")
    barcode_qr = models.CharField(max_length=100, unique=True, verbose_name="الباركود / QR")
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES, verbose_name="نوع الصنف")
    
    average_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="متوسط التكلفة")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر البيع")
    requires_imei = models.BooleanField(default=False, verbose_name="يتطلب سيريال/IMEI")

    class Meta:
        verbose_name = "صنف / منتج"
        verbose_name_plural = "دليل الأصناف والمنتجات"

    def __str__(self):
        return self.name

class Stock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="الصنف")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name="المخزن")
    quantity = models.IntegerField(default=0, verbose_name="الكمية")

    class Meta:
        verbose_name = "كمية مخزون"
        verbose_name_plural = "كميات المخزون"

    def __str__(self):
        return f"{self.product.name} - {self.warehouse.name}: {self.quantity}"

class Device(models.Model):
    CONDITIONS = (('new', 'جديد'), ('used', 'مستعمل'))
    STORAGE_CHOICES = (
        ('128', '128 جيجا'),
        ('256', '256 جيجا'),
        ('512', '512 جيجا'),
        ('1gb', '1 جيجا'),
        ('1tb', '1 تيرا'),
        ('other', 'أخرى'),
    )
    RAM_CHOICES = (
        ('3', '3 رام'),
        ('4', '4 رام'),
        ('6', '6 رام'),
        ('8', '8 رام'),
        ('12', '12 رام'),
        ('other', 'أخرى'),
    )
    USED_STATUS_CHOICES = (
        ('like_new', 'كسر زيرو'),
        ('good_condition', 'مستعمل بحالة جيدة'),
        ('other', 'أخرى'),
    )
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="الموديل/الصنف")
    imei = models.CharField(max_length=50, unique=True, verbose_name="السيريال/IMEI 1")
    imei2 = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="السيريال 2/IMEI 2")
    condition = models.CharField(max_length=20, choices=CONDITIONS, verbose_name="الحالة")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name="المخزن الحالي")
    is_sold = models.BooleanField(default=False, verbose_name="مباع؟")
    
    purchased_from = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="تم الشراء من (للمستعمل)")
    cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="تكلفة الشراء")
    
    # تفاصيل حالة ومواصفات الأجهزة المستعملة
    storage = models.CharField(max_length=20, choices=STORAGE_CHOICES, blank=True, null=True, verbose_name="المساحة")
    ram = models.CharField(max_length=20, choices=RAM_CHOICES, blank=True, null=True, verbose_name="الرام")
    used_status = models.CharField(max_length=20, choices=USED_STATUS_CHOICES, blank=True, null=True, verbose_name="حالة الجهاز المستعمل")
    has_box = models.BooleanField(default=False, verbose_name="يوجد كرتونة")
    has_charger = models.BooleanField(default=False, verbose_name="يوجد شاحن")
    is_tax_paid = models.BooleanField(default=False, verbose_name="خالص الضريبة")
    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات الجهاز")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "جهاز موبايل"
        verbose_name_plural = "الأجهزة"

    def __str__(self):
        if self.imei2:
            return f"{self.product.name} - {self.imei} / {self.imei2}"
        return f"{self.product.name} - {self.imei}"

class DeviceAttachment(models.Model):
    ATTACHMENT_TYPES = (
        ('id_front', 'صورة البطاقة - وجه'),
        ('id_back', 'صورة البطاقة - ظهر'),
        ('contract', 'عقد مبايعة / إقرار تنازل'),
        ('device_condition', 'صورة لحالة الجهاز'),
        ('other', 'أخرى'),
    )
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='attachments')
    attachment_type = models.CharField(max_length=20, choices=ATTACHMENT_TYPES, blank=True, null=True, verbose_name="نوع المرفق")
    image = models.ImageField(upload_to='used_devices_docs/%Y/%m/', blank=True, null=True, verbose_name="الصورة")
    notes = models.CharField(max_length=255, blank=True, null=True, verbose_name="ملاحظات")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مرفق جهاز"
        verbose_name_plural = "مرفقات الأجهزة"

# ==========================================
# 4. المشتريات وحركة المخزون (Purchases & Transfers)
# ==========================================
class PurchaseInvoice(models.Model):
    supplier = models.ForeignKey(Contact, on_delete=models.PROTECT, limit_choices_to={'contact_type': 'supplier'}, verbose_name="المورد")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="مستلم البضاعة")
    invoice_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الفاتورة")
    supplier_invoice_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="رقم فاتورة المورد")
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, related_name='purchase_invoices', null=True, blank=True, verbose_name="الخزينة المسدد عليها")

    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الإجمالي")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الخصم")
    
    # المعالجة الضريبية الدقيقة لتعاملات الموردين (B2B)
    deduction_addition_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="ضريبة الخصم والإضافة")
    
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الصافي للدفع")
    
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'نقدي (كاش)'),
        ('credit', 'آجل بالكامل'),
        ('partial', 'مسدد جزئياً'),
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash', verbose_name="طريقة الدفع")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="المبلغ المدفوع")

    @property
    def remaining_amount(self):
        return self.net_amount - self.paid_amount

    class Meta:
        verbose_name = "فاتورة مشتريات"
        verbose_name_plural = "فواتير المشتريات"

class PurchaseItem(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='items', verbose_name="فاتورة الشراء")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="الصنف")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="المخزن")
    quantity = models.IntegerField(verbose_name="الكمية")
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="تكلفة الوحدة")
    imei_list = models.TextField(blank=True, null=True, help_text="للسيريالات مفصولة بفاصلة", verbose_name="قائمة السيريالات/IMEI")
    
    # المواصفات الإضافية للأجهزة الموردة
    storage = models.CharField(max_length=20, choices=Device.STORAGE_CHOICES, blank=True, null=True, verbose_name="المساحة")
    ram = models.CharField(max_length=20, choices=Device.RAM_CHOICES, blank=True, null=True, verbose_name="الرام")
    is_tax_paid = models.BooleanField(default=False, verbose_name="خالص الضريبة")

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.product and self.product.requires_imei:
            if not self.imei_list:
                raise ValidationError({'imei_list': "المنتج المختار يتطلب إدخال سيريالات (IMEI)."})
            imeis = [i.strip() for i in self.imei_list.split(',') if i.strip()]
            if len(imeis) != self.quantity:
                raise ValidationError({
                    'imei_list': f"عدد السيريالات المدخلة ({len(imeis)}) لا يتطابق مع الكمية المحددة ({self.quantity})."
                })

    class Meta:
        verbose_name = "بند مشتريات"
        verbose_name_plural = "بنود المشتريات"

class StockTransfer(models.Model):
    STATUS_CHOICES = (('pending', 'قيد النقل'), ('completed', 'تم الاستلام'))
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_out', verbose_name="من مخزن")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_in', verbose_name="إلى مخزن")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='transfers_created', verbose_name="منشئ التحويل")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="حالة التحويل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التحويل")

    class Meta:
        verbose_name = "حركة تحويل مخزن"
        verbose_name_plural = "حركات تحويل المخازن"

class StockTransferItem(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items', verbose_name="حركة التحويل")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="الصنف")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="جهاز موبايل")
    quantity = models.IntegerField(default=1, verbose_name="الكمية")

    class Meta:
        verbose_name = "بند تحويل مخزن"
        verbose_name_plural = "بنود تحويل المخازن"

# ==========================================
# 5. إدارة الخزينة والورديات (Cash & Shifts)
# ==========================================
class CashShift(models.Model):
    STATUS_CHOICES = (('open', 'مفتوحة'), ('closed', 'مغلقة'))
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="الكاشير")
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="وقت فتح الوردية")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="وقت إغلاق الوردية")
    
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, related_name='shifts', null=True, blank=True, verbose_name="الخزينة")
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="رصيد البداية")
    expected_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الرصيد النقدي المتوقع")
    actual_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="الرصيد الفعلي المسلم")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name="حالة الوردية")

    class Meta:
        verbose_name = "وردية خزينة"
        verbose_name_plural = "ورديات الخزينة"

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="بند المصروف")

    class Meta:
        verbose_name = "تصنيف مصروف"
        verbose_name_plural = "تصنيفات المصروفات"

    def __str__(self):
        return self.name

class Expense(models.Model):
    shift = models.ForeignKey(CashShift, on_delete=models.CASCADE, related_name='expenses', verbose_name="الوردية")
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة المنصرف منها")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, verbose_name="بند المصروف")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="التفاصيل/الوصف")

    class Meta:
        verbose_name = "مصروف تشغيلي"
        verbose_name_plural = "المصروفات التشغيلية"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.treasury:
            # خصم قيمة المصروف من رصيد الخزينة
            self.treasury.balance -= self.amount
            self.treasury.save()

    def __str__(self):
        return f"{self.category.name}: {self.amount}"

# ==========================================
# 6. المبيعات ونقاط البيع (Sales & POS)
# ==========================================
class SaleInvoice(models.Model):
    shift = models.ForeignKey(CashShift, on_delete=models.PROTECT, verbose_name="الوردية")
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="الكاشير")
    customer = models.ForeignKey(Contact, on_delete=models.PROTECT, verbose_name="العميل")
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الفاتورة")
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الإجمالي")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الخصم")
    
    # Trade-in (استبدال جهاز قديم)
    traded_in_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='traded_in_invoice', verbose_name="الجهاز المستبدل")
    trade_in_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="قيمة الاستبدال")
    
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الصافي")

    PAYMENT_METHOD_CHOICES = (
        ('cash', 'نقدي (كاش)'),
        ('credit', 'آجل بالكامل'),
        ('partial', 'مسدد جزئياً'),
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash', verbose_name="طريقة الدفع")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="المبلغ المدفوع")

    @property
    def remaining_amount(self):
        return self.net_amount - self.paid_amount

    @property
    def is_fully_paid(self):
        return self.remaining_amount <= 0

    class Meta:
        verbose_name = "فاتورة مبيعات"
        verbose_name_plural = "فواتير المبيعات"

    def __str__(self):
        return f"فاتورة #{self.id} - {self.customer.name}"

class SaleItem(models.Model):
    invoice = models.ForeignKey(SaleInvoice, on_delete=models.CASCADE, related_name='items', verbose_name="الفاتورة")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="الصنف")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="المخزن")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="جهاز موبايل")
    quantity = models.IntegerField(default=1, verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر الوحدة")

    class Meta:
        verbose_name = "بند مبيعات"
        verbose_name_plural = "بنود المبيعات"

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"

class Payment(models.Model):
    PAYMENT_METHODS = (('cash', 'نقدي'), ('visa', 'فيزا'), ('wallet', 'محفظة إلكترونية'))
    invoice = models.ForeignKey(SaleInvoice, on_delete=models.CASCADE, related_name='payments', verbose_name="الفاتورة")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, verbose_name="طريقة الدفع")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    transaction_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم المعاملة")

    class Meta:
        verbose_name = "دفعة مالية"
        verbose_name_plural = "الدفعات المالية"

    def __str__(self):
        return f"{self.get_payment_method_display()}: {self.amount}"

# ==========================================
# 7. دورة الصيانة (Maintenance)
# ==========================================
class RepairTicket(models.Model):
    STATUS_CHOICES = (
        ('pending', 'قيد الانتظار'), ('in_progress', 'جاري العمل'),
        ('waiting_parts', 'في انتظار قطع الغيار'), ('done', 'جاهز للتسليم'), ('delivered', 'تم التسليم')
    )
    customer = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="العميل")
    technician = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="الفني المختص")
    device_model = models.CharField(max_length=100, verbose_name="موديل الجهاز")
    device_imei = models.CharField(max_length=50, blank=True, null=True, verbose_name="السيريال/IMEI")
    issue_description = models.TextField(verbose_name="وصف العطل")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="حالة التذكرة")
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="التكلفة التقديرية")
    labor_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="مصنعية")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الدخول")

    class Meta:
        verbose_name = "تذكرة صيانة"
        verbose_name_plural = "تذاكر الصيانة"

    def __str__(self):
        return f"تذكرة صيانة #{self.id} - {self.device_model}"

    @property
    def total_cost(self):
        parts_total = sum(part.price * part.quantity for part in self.parts_used.all())
        return self.labor_cost + parts_total

    @property
    def parts_cost_total(self):
        return sum(part.product.average_cost * part.quantity for part in self.parts_used.all())

    @property
    def parts_price_total(self):
        return sum(part.price * part.quantity for part in self.parts_used.all())

    @property
    def parts_profit(self):
        return self.parts_price_total - self.parts_cost_total

    @property
    def ticket_profit(self):
        return self.labor_cost + self.parts_profit

class RepairPartUsed(models.Model):
    ticket = models.ForeignKey(RepairTicket, on_delete=models.CASCADE, related_name='parts_used', verbose_name="التذكرة")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="قطعة الغيار")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="مخزن السحب")
    quantity = models.IntegerField(default=1, verbose_name="الكمية")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر البيع")

    class Meta:
        verbose_name = "قطعة غيار مستهلكة"
        verbose_name_plural = "قطع الغيار المستهلكة في الصيانة"

    def __str__(self):
        return f"{self.product.name} ({self.quantity}) لـ #{self.ticket.id}"

# ==========================================
# 8. خدمة ما بعد البيع (After-Sales)
# ==========================================
class Warranty(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, verbose_name="الجهاز")
    customer = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="العميل")
    invoice = models.ForeignKey(SaleInvoice, on_delete=models.CASCADE, verbose_name="فاتورة البيع")
    duration_days = models.IntegerField(default=14, verbose_name="مدة الضمان (بالأيام)")
    start_date = models.DateField(auto_now_add=True, verbose_name="تاريخ بدء الضمان")

    class Meta:
        verbose_name = "ضمان جهاز"
        verbose_name_plural = "الضمانات"
    
    @property
    def is_valid(self):
        return timezone.now().date() <= (self.start_date + timedelta(days=self.duration_days))

    def __str__(self):
        return f"ضمان {self.device.imei} - {self.customer.name}"



class NotificationLog(models.Model):
    STATUS_CHOICES = (
        ('queued',  'في الانتظار'),
        ('sent',    'تم الإرسال'),
        ('failed',  'فشل الإرسال'),
        ('skipped', 'تم التخطي (مغلق)'),
    )
    customer = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="العميل")
    ticket = models.ForeignKey(RepairTicket, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="تذكرة الصيانة")
    notification_type = models.CharField(max_length=20, choices=(('whatsapp', 'واتساب'), ('sms', 'SMS')), default='whatsapp', verbose_name="نوع الإشعار")
    message_body = models.TextField(verbose_name="محتوى الرسالة")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت الإرسال")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', verbose_name="الحالة")
    error_message = models.TextField(blank=True, null=True, verbose_name="رسالة الخطأ")
    retry_count = models.PositiveSmallIntegerField(default=0, verbose_name="عدد المحاولات")

    class Meta:
        verbose_name = "سجل إشعار"
        verbose_name_plural = "سجلات الإشعارات"
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.get_notification_type_display()} to {self.customer.name} [{self.get_status_display()}]"


class NotificationSettings(models.Model):
    """
    Singleton model لإعدادات الإشعارات.
    رقم الواتساب المرسل + قوالب الرسائل لكل حالة تذكرة.
    """
    # اعدادات الاتصال
    whatsapp_enabled = models.BooleanField(
        default=False,
        verbose_name="تفعيل إشعارات الواتساب",
        help_text="فعّل فقط بعد مسح QR Code وربط الهاتف بالسيرفر."
    )
    sender_phone = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name="رقم الواتساب المرسل",
        help_text="الصيغة الدولية مثال: +201012345678"
    )
    branch_name = models.CharField(
        max_length=100, default="المحل",
        verbose_name="اسم الفرع / المحل",
        help_text="سيظهر في نصوص الرسائل تلقائياً."
    )
    delay_min_seconds = models.PositiveSmallIntegerField(default=15, verbose_name="الحد الادنى للتاخير (ثانية)")
    delay_max_seconds = models.PositiveSmallIntegerField(default=45, verbose_name="الحد الاقصى للتاخير (ثانية)")

    # قوالب الرسائل - المتغيرات: {customer_name} {device_model} {ticket_id} {branch_name} {status_display} {time}
    msg_pending_enabled = models.BooleanField(default=False, verbose_name="ارسال عند: قيد الانتظار")
    msg_pending = models.TextField(
        default="اهلاً {customer_name}، تم استلام جهازك {device_model} في {branch_name}. رقم تذكرتك: #{ticket_id}",
        verbose_name="قالب: قيد الانتظار"
    )
    msg_in_progress_enabled = models.BooleanField(default=True, verbose_name="ارسال عند: جاري العمل")
    msg_in_progress = models.TextField(
        default="اهلاً {customer_name}، بدأ فريقنا العمل على جهازك {device_model}. رقم التذكرة: #{ticket_id} — {branch_name}",
        verbose_name="قالب: جاري العمل"
    )
    msg_waiting_parts_enabled = models.BooleanField(default=True, verbose_name="ارسال عند: انتظار قطع الغيار")
    msg_waiting_parts = models.TextField(
        default="اهلاً {customer_name}، جهازك {device_model} يحتاج قطعة غيار قيد التوفير. سنبلغك فور الانتهاء. رقم التذكرة: #{ticket_id}",
        verbose_name="قالب: انتظار قطع الغيار"
    )
    msg_done_enabled = models.BooleanField(default=True, verbose_name="ارسال عند: جاهز للتسليم")
    msg_done = models.TextField(
        default="جهازك {device_model} جاهز للاستلام من {branch_name}! رقم التذكرة: #{ticket_id}. في انتظارك {customer_name}",
        verbose_name="قالب: جاهز للتسليم"
    )
    msg_delivered_enabled = models.BooleanField(default=False, verbose_name="ارسال عند: تم التسليم")
    msg_delivered = models.TextField(
        default="شكراً {customer_name} على ثقتك في {branch_name}. رقم التذكرة: #{ticket_id}",
        verbose_name="قالب: تم التسليم"
    )

    class Meta:
        verbose_name = "اعدادات الاشعارات"
        verbose_name_plural = "اعدادات الاشعارات"

    def __str__(self):
        status = "مفعل" if self.whatsapp_enabled else "موقف"
        return f"اعدادات الاشعارات — الواتساب {status}"

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def render_template(self, template_key, ticket):
        """يبني نص الرسالة بإدخال متغيرات التذكرة."""
        from django.utils import timezone as tz
        template = getattr(self, template_key, "")
        return template.format(
            customer_name=ticket.customer.name,
            device_model=ticket.device_model,
            ticket_id=ticket.id,
            branch_name=self.branch_name,
            status_display=ticket.get_status_display(),
            time=tz.localtime(tz.now()).strftime("%Y/%m/%d %H:%M"),
        )


# ==========================================
# 9. نظام الخزن والعهد (Treasury & Safes)
# ==========================================
class Treasury(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم الخزينة")
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="رصيد أول المدة")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="الرصيد الحالي")
    is_active = models.BooleanField(default=True, verbose_name="نشطة")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='treasuries', verbose_name="المستخدم المسؤول")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "خزينة"
        verbose_name_plural = "الخزن"

    def __str__(self):
        return f"{self.name} ({self.user.username}) - رصيد: {self.balance} ج.م"

    def save(self, *args, **kwargs):
        # في حال الإنشاء لأول مرة، نجعل الرصيد الحالي يساوي رصيد أول المدة
        if not self.pk:
            self.balance = self.opening_balance
        super().save(*args, **kwargs)

# ==========================================
# 10. شؤون الموظفين والرواتب (HR & Payroll)
# ==========================================
class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile', verbose_name="حساب المستخدم")
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="قيمة ساعة العمل العادية")
    daily_working_hours = models.DecimalField(max_digits=4, decimal_places=2, default=8.00, verbose_name="ساعات العمل اليومية")
    shift_start_time = models.TimeField(null=True, blank=True, verbose_name="ميعاد الحضور")
    shift_end_time = models.TimeField(null=True, blank=True, verbose_name="ميعاد الانصراف")
    deduction_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="قيمة الخصم للساعة")
    overtime_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="قيمة الإضافي للساعة")
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الراتب الأساسي (اختياري)")
    is_active = models.BooleanField(default=True, verbose_name="على رأس العمل")

    class Meta:
        verbose_name = "ملف الموظف"
        verbose_name_plural = "ملفات الموظفين"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

class Attendance(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='attendances', verbose_name="الموظف")
    date = models.DateField(default=timezone.now, verbose_name="التاريخ")
    check_in = models.DateTimeField(null=True, blank=True, verbose_name="وقت الحضور")
    check_out = models.DateTimeField(null=True, blank=True, verbose_name="وقت الانصراف")
    delay_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ساعات التأخير")
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="الساعات الإضافية")
    status = models.CharField(max_length=20, choices=(('present', 'حاضر'), ('absent', 'غائب'), ('leave', 'إجازة')), default='present', verbose_name="الحالة")

    class Meta:
        verbose_name = "سجل حضور"
        verbose_name_plural = "سجلات الحضور والانصراف"
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"حضور {self.employee.user.username} - {self.date}"

class Payroll(models.Model):
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='payrolls', verbose_name="الموظف")
    month = models.IntegerField(verbose_name="الشهر")
    year = models.IntegerField(verbose_name="السنة")
    total_worked_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name="إجمالي ساعات العمل")
    total_delay_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="إجمالي ساعات التأخير")
    total_overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="إجمالي الساعات الإضافية")
    base_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="المستحق الأساسي")
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="مكافأة الإضافي")
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="إجمالي الخصومات")
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الراتب الصافي")
    is_paid = models.BooleanField(default=False, verbose_name="تم الصرف")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الصرف")

    class Meta:
        verbose_name = "مسير راتب"
        verbose_name_plural = "مسيرات الرواتب"
        unique_together = ('employee', 'month', 'year')

    def __str__(self):
        return f"راتب {self.employee.user.username} - {self.month}/{self.year}"

# ==========================================
# 12. المرتجعات (Returns)
# ==========================================
class SaleReturn(models.Model):
    sale_invoice = models.ForeignKey(SaleInvoice, on_delete=models.CASCADE, related_name='returns', verbose_name="فاتورة البيع الأصلية")
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, verbose_name="الخزينة المخصوم منها")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="بواسطة")
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ المرتجع")
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ المسترد للعميل")
    notes = models.TextField(blank=True, null=True, verbose_name="سبب الاسترجاع")

    class Meta:
        verbose_name = "مرتجع مبيعات"
        verbose_name_plural = "مرتجعات المبيعات"

    def __str__(self):
        return f"مرتجع مبيعات #{self.id} لفاتورة #{self.sale_invoice.id}"

class SaleReturnItem(models.Model):
    return_invoice = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items', verbose_name="فاتورة المرتجع")
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, verbose_name="البند الأصلي")
    quantity = models.IntegerField(default=1, verbose_name="الكمية المرتجعة")
    
    class Meta:
        verbose_name = "بند مرتجع مبيعات"
        verbose_name_plural = "بنود مرتجعات المبيعات"

    def __str__(self):
        return f"{self.sale_item.product.name} ({self.quantity})"

class PurchaseReturn(models.Model):
    purchase_invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='returns', verbose_name="فاتورة الشراء الأصلية")
    treasury = models.ForeignKey('Treasury', on_delete=models.PROTECT, verbose_name="الخزينة المودع بها")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="بواسطة")
    date_created = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ المرتجع")
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ المسترد من المورد")
    notes = models.TextField(blank=True, null=True, verbose_name="سبب الاسترجاع")

    class Meta:
        verbose_name = "مرتجع مشتريات"
        verbose_name_plural = "مرتجعات المشتريات"

    def __str__(self):
        return f"مرتجع مشتريات #{self.id} لفاتورة #{self.purchase_invoice.id}"

class PurchaseReturnItem(models.Model):
    return_invoice = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='items', verbose_name="فاتورة المرتجع")
    purchase_item = models.ForeignKey(PurchaseItem, on_delete=models.CASCADE, verbose_name="البند الأصلي")
    quantity = models.IntegerField(default=1, verbose_name="الكمية المرتجعة")
    
    class Meta:
        verbose_name = "بند مرتجع مشتريات"
        verbose_name_plural = "بنود مرتجعات المشتريات"

    def __str__(self):
        return f"{self.purchase_item.product.name} ({self.quantity})"
