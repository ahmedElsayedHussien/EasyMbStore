from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from erp.models import (
    Product, Stock, Device, PurchaseItem, SaleItem, SaleInvoice,
    StockTransfer, StockTransferItem, RepairPartUsed, CashShift, Payment, Expense
)

# ==========================================
# 1. المشتريات وتكلفة البضاعة (Purchases & Moving Average Cost)
# ==========================================
@receiver(post_save, sender=PurchaseItem)
def handle_purchase_item_saved(sender, instance, created, **kwargs):
    if not created:
        return  # في هذا النظام، نفترض إدخال بنود المشتريات مرة واحدة فقط لتبسيط منطق المتوسط المتحرك

    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity
    cost = instance.unit_cost

    # أ. حساب متوسط التكلفة المتحرك (Moving Average Cost)
    # نحسب الكمية الحالية في الشركة بالكامل قبل إضافة الكمية الجديدة
    if product.requires_imei:
        current_qty = Device.objects.filter(product=product, is_sold=False).count()
    else:
        current_qty = Stock.objects.filter(product=product).aggregate(total=models.Sum('quantity'))['total'] or 0

    old_avg = product.average_cost
    total_qty = current_qty + qty

    if total_qty > 0:
        new_avg = ((current_qty * old_avg) + (qty * cost)) / total_qty
    else:
        new_avg = cost

    product.average_cost = new_avg
    product.save(update_fields=['average_cost'])

    # ب. زيادة المخزون أو إنشاء الأجهزة
    if product.requires_imei:
        if instance.imei_list:
            imeis = [i.strip() for i in instance.imei_list.split(',') if i.strip()]
            for imei_entry in imeis:
                if '/' in imei_entry:
                    imei_parts = [p.strip() for p in imei_entry.split('/') if p.strip()]
                    imei1 = imei_parts[0]
                    imei2 = imei_parts[1] if len(imei_parts) > 1 else None
                else:
                    imei1 = imei_entry
                    imei2 = None
                
                # البحث عن جهاز موجود يطابق أي من السيريالين
                device = None
                if imei1:
                    device = Device.objects.filter(models.Q(imei=imei1) | models.Q(imei2=imei1)).first()
                if not device and imei2:
                    device = Device.objects.filter(models.Q(imei=imei2) | models.Q(imei2=imei2)).first()
                
                if device:
                    device.product = product
                    device.condition = 'new'
                    device.warehouse = warehouse
                    device.is_sold = False
                    device.purchased_from = instance.invoice.supplier
                    device.cost = cost
                    device.storage = instance.storage
                    device.ram = instance.ram
                    device.is_tax_paid = instance.is_tax_paid
                    if imei2:
                        device.imei2 = imei2
                    device.save()
                else:
                    Device.objects.create(
                        product=product,
                        imei=imei1,
                        imei2=imei2,
                        condition='new',
                        warehouse=warehouse,
                        is_sold=False,
                        purchased_from=instance.invoice.supplier,
                        cost=cost,
                        storage=instance.storage,
                        ram=instance.ram,
                        is_tax_paid=instance.is_tax_paid
                    )
    else:
        stock, _ = Stock.objects.get_or_create(product=product, warehouse=warehouse)
        stock.quantity += qty
        stock.save()


@receiver(post_delete, sender=PurchaseItem)
def handle_purchase_item_deleted(sender, instance, **kwargs):
    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity

    if product.requires_imei:
        if instance.imei_list:
            imeis = [i.strip() for i in instance.imei_list.split(',') if i.strip()]
            all_imeis = []
            for imei_entry in imeis:
                if '/' in imei_entry:
                    all_imeis.extend([p.strip() for p in imei_entry.split('/') if p.strip()])
                else:
                    all_imeis.append(imei_entry)
            # نقوم بحذف الأجهزة التي تم شراؤها بهذه الفاتورة ولم يتم بيعها بعد
            Device.objects.filter(
                models.Q(imei__in=all_imeis) | models.Q(imei2__in=all_imeis),
                is_sold=False
            ).delete()
    else:
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            stock.quantity -= qty
            stock.save()
        except Stock.DoesNotExist:
            pass


# ==========================================
# 2. المبيعات ونقاط البيع واستبدال الأجهزة (Sales & POS)
# ==========================================
@receiver(post_save, sender=SaleItem)
def handle_sale_item_saved(sender, instance, created, **kwargs):
    if not created:
        return

    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity

    if product.requires_imei:
        if instance.device:
            instance.device.is_sold = True
            instance.device.save(update_fields=['is_sold'])
    else:
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            stock.quantity -= qty
            stock.save()
        except Stock.DoesNotExist:
            # في حال عدم وجود سجل مخزون، نقوم بإنشاء سجل بالسالب (كإجراء احترازي)
            Stock.objects.create(product=product, warehouse=warehouse, quantity=-qty)


@receiver(post_delete, sender=SaleItem)
def handle_sale_item_deleted(sender, instance, **kwargs):
    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity

    if product.requires_imei:
        if instance.device:
            instance.device.is_sold = False
            instance.device.save(update_fields=['is_sold'])
    else:
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            stock.quantity += qty
            stock.save()
        except Stock.DoesNotExist:
            Stock.objects.create(product=product, warehouse=warehouse, quantity=qty)


@receiver(post_save, sender=SaleInvoice)
def handle_sale_invoice_saved(sender, instance, created, **kwargs):
    # في حال وجود جهاز مستبدل (Trade-in)
    if instance.traded_in_device:
        device = instance.traded_in_device
        device.is_sold = False
        device.purchased_from = instance.customer
        device.cost = instance.trade_in_value
        device.condition = 'used'
        
        # نضع الجهاز المستعمل في مخزن أول بند مبيعات، أو نتركه في مخزنه الحالي
        first_item = instance.items.first()
        if first_item:
            device.warehouse = first_item.warehouse
        device.save()


# ==========================================
# 3. حركات تحويل المخزون (Stock Transfers)
# ==========================================
@receiver(pre_save, sender=StockTransfer)
def handle_stock_transfer_pre_save(sender, instance, **kwargs):
    if instance.id:
        try:
            old_transfer = StockTransfer.objects.get(id=instance.id)
            # عندما تتحول حالة التحويل من قيد النقل إلى تم الاستلام
            if old_transfer.status == 'pending' and instance.status == 'completed':
                for item in instance.items.all():
                    product = item.product
                    qty = item.quantity

                    if product.requires_imei:
                        if item.device:
                            item.device.warehouse = instance.to_warehouse
                            item.device.save(update_fields=['warehouse'])
                    else:
                        # خصم من المخزن المرسل
                        from_stock, _ = Stock.objects.get_or_create(product=product, warehouse=instance.from_warehouse)
                        from_stock.quantity -= qty
                        from_stock.save()

                        # إضافة إلى المخزن المستقبل
                        to_stock, _ = Stock.objects.get_or_create(product=product, warehouse=instance.to_warehouse)
                        to_stock.quantity += qty
                        to_stock.save()
        except StockTransfer.DoesNotExist:
            pass


# ==========================================
# 4. قطع الغيار في الصيانة (Maintenance Parts)
# ==========================================
@receiver(post_save, sender=RepairPartUsed)
def handle_repair_part_used_saved(sender, instance, created, **kwargs):
    if not created:
        return

    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity

    if product.requires_imei:
        # إذا كانت قطعة الغيار تتطلب سيريال (حالة نادرة جداً)
        device = Device.objects.filter(product=product, warehouse=warehouse, is_sold=False).first()
        if device:
            device.is_sold = True
            device.save(update_fields=['is_sold'])
    else:
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            stock.quantity -= qty
            stock.save()
        except Stock.DoesNotExist:
            Stock.objects.create(product=product, warehouse=warehouse, quantity=-qty)


@receiver(post_delete, sender=RepairPartUsed)
def handle_repair_part_used_deleted(sender, instance, **kwargs):
    product = instance.product
    warehouse = instance.warehouse
    qty = instance.quantity

    if product.requires_imei:
        device = Device.objects.filter(product=product, warehouse=warehouse, is_sold=True).first()
        if device:
            device.is_sold = False
            device.save(update_fields=['is_sold'])
    else:
        try:
            stock = Stock.objects.get(product=product, warehouse=warehouse)
            stock.quantity += qty
            stock.save()
        except Stock.DoesNotExist:
            Stock.objects.create(product=product, warehouse=warehouse, quantity=qty)


# ==========================================
# 5. إدارة الخزينة والورديات (Shift & Expenses Balance)
# ==========================================
@receiver(pre_save, sender=CashShift)
def handle_shift_pre_save(sender, instance, **kwargs):
    # حساب الرصيد المتوقع إغلاق الوردية به تلقائياً
    if instance.id:
        cash_sales = Payment.objects.filter(
            invoice__shift=instance,
            payment_method='cash'
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        total_expenses = Expense.objects.filter(
            shift=instance
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        instance.expected_closing_balance = instance.opening_balance + cash_sales - total_expenses
    else:
        instance.expected_closing_balance = instance.opening_balance


def trigger_shift_recalculation(shift):
    if shift and shift.status == 'open':
        shift.save()  # سيقوم pre_save بإعادة الحساب تلقائياً


@receiver(post_save, sender=Payment)
def handle_payment_saved(sender, instance, **kwargs):
    if instance.payment_method == 'cash':
        trigger_shift_recalculation(instance.invoice.shift)


@receiver(post_delete, sender=Payment)
def handle_payment_deleted(sender, instance, **kwargs):
    if instance.payment_method == 'cash':
        trigger_shift_recalculation(instance.invoice.shift)


@receiver(post_save, sender=Expense)
def handle_expense_saved(sender, instance, **kwargs):
    trigger_shift_recalculation(instance.shift)


@receiver(post_delete, sender=Expense)
def handle_expense_deleted(sender, instance, **kwargs):
    trigger_shift_recalculation(instance.shift)
