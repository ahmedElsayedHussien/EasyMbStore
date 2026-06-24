from django.contrib import admin
from erp.models import (
    StoreSetting, Contact, Warehouse, Product, Stock, Device, DeviceAttachment,
    PurchaseInvoice, PurchaseItem, StockTransfer, StockTransferItem,
    CashShift, ExpenseCategory, Expense, SaleInvoice, SaleItem, Payment,
    RepairTicket, RepairPartUsed, Warranty, NotificationLog, NotificationSettings,
    Treasury, TreasuryTransaction, CommissionRule, SalesTarget
)

# 1. إعدادات المحل (Singleton Settings)
@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'whatsapp_api_key', 'sms_api_key')
    
    # منع إنشاء سجل إضافي إذا كان هناك سجل موجود بالفعل لضمان Singleton
    def has_add_permission(self, request):
        if StoreSetting.objects.exists():
            return False
        return True

# 2. جهات الاتصال
@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'contact_type', 'national_id')
    list_filter = ('contact_type',)
    search_fields = ('name', 'phone', 'national_id')

# 3. المخازن والمنتجات والمخزون
@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'barcode_qr', 'product_type', 'average_cost', 'selling_price', 'requires_imei')
    list_filter = ('product_type', 'requires_imei')
    search_fields = ('name', 'barcode_qr')

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'quantity')
    list_filter = ('warehouse', 'product__product_type')
    search_fields = ('product__name', 'product__barcode_qr')

# مرفقات الأجهزة المستعملة كـ TabularInline
class DeviceAttachmentInline(admin.TabularInline):
    model = DeviceAttachment
    extra = 1

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('product', 'imei', 'condition', 'warehouse', 'is_sold', 'cost', 'purchased_from')
    list_filter = ('condition', 'is_sold', 'warehouse')
    search_fields = ('imei', 'product__name')
    inlines = [DeviceAttachmentInline]

# 4. المشتريات
class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1

@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'supplier_invoice_number', 'total_amount', 'discount', 'deduction_addition_tax', 'net_amount', 'invoice_date')
    list_filter = ('supplier', 'invoice_date')
    search_fields = ('supplier_invoice_number', 'supplier__name')
    inlines = [PurchaseItemInline]

# 5. تحويل المخازن
class StockTransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 1

@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_warehouse', 'to_warehouse', 'created_by', 'status', 'created_at')
    list_filter = ('status', 'from_warehouse', 'to_warehouse')
    inlines = [StockTransferItemInline]

# 6. الورديات والمصروفات
class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 1

@admin.register(CashShift)
class CashShiftAdmin(admin.ModelAdmin):
    list_display = ('id', 'cashier', 'start_time', 'end_time', 'opening_balance', 'expected_closing_balance', 'actual_cash', 'status')
    list_filter = ('status', 'cashier')
    inlines = [ExpenseInline]

admin.site.register(ExpenseCategory)

# 7. المبيعات و POS
class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

@admin.register(SaleInvoice)
class SaleInvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'shift', 'cashier', 'customer', 'total_amount', 'discount', 'trade_in_value', 'net_amount', 'date_created')
    list_filter = ('date_created', 'cashier')
    search_fields = ('customer__name', 'id')
    inlines = [SaleItemInline, PaymentInline]

# 8. الصيانة والتصليح
class RepairPartUsedInline(admin.TabularInline):
    model = RepairPartUsed
    extra = 1

@admin.register(RepairTicket)
class RepairTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'technician', 'device_model', 'device_imei', 'status', 'labor_cost')
    list_filter = ('status', 'technician')
    search_fields = ('customer__name', 'device_model', 'device_imei')
    inlines = [RepairPartUsedInline]

# 9. الضمان والإشعارات
@admin.register(Warranty)
class WarrantyAdmin(admin.ModelAdmin):
    list_display = ('device', 'customer', 'invoice', 'duration_days', 'start_date', 'is_valid')
    list_filter = ('start_date',)
    search_fields = ('device__imei', 'customer__name')

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('customer', 'notification_type', 'sent_at', 'status')
    list_filter = ('notification_type', 'status')
    search_fields = ('customer__name', 'message_body')

@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ('sender_phone', 'whatsapp_enabled', 'delay_min_seconds', 'delay_max_seconds')
    
    def has_add_permission(self, request):
        if NotificationSettings.objects.exists():
            return False
        return True

@admin.register(Treasury)
class TreasuryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'opening_balance', 'balance', 'is_active', 'created_at')
    list_filter = ('is_active', 'user')
    search_fields = ('name', 'user__username')



@admin.register(TreasuryTransaction)
class TreasuryTransactionAdmin(admin.ModelAdmin):
    list_display = ('treasury', 'transaction_type', 'amount', 'date', 'user')
    list_filter = ('transaction_type', 'treasury', 'date')
    search_fields = ('description',)
    readonly_fields = ('date',)

@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = ('product_type', 'sales_milestone', 'commission_amount')
    search_fields = ('product_type',)

@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ('user', 'period', 'target_amount', 'date')
    list_filter = ('period', 'user', 'date')
