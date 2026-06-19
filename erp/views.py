# -*- coding: windows-1256 -*-
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.exceptions import PermissionDenied
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required as django_permission_required
from functools import wraps
def permission_required(perm, login_url=None, raise_exception=False):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if raise_exception:
                perms = [perm] if isinstance(perm, str) else perm
                if not request.user.has_perms(perms):
                    from django.core.exceptions import PermissionDenied
                    friendly_names = {
                        'erp.add_saleinvoice': 'إنشاء فواتير البيع (نقطة البيع) [erp.add_saleinvoice]',
                        'erp.view_saleinvoice': 'عرض فواتير البيع [erp.view_saleinvoice]',
                        'erp.add_device': 'شراء الأجهزة المستعملة وتعديلها [erp.add_device]',
                        'erp.view_device': 'عرض الأجهزة وسجلها التاريخي [erp.view_device]',
                        'erp.view_purchaseinvoice': 'عرض فواتير الشراء [erp.view_purchaseinvoice]',
                        'erp.add_purchaseinvoice': 'تسجيل فواتير الشراء [erp.add_purchaseinvoice]',
                        'erp.view_stocktransfer': 'عرض حركات تحويل المخازن [erp.view_stocktransfer]',
                        'erp.add_stocktransfer': 'إنشاء حركات تحويل المخازن [erp.add_stocktransfer]',
                        'erp.change_stocktransfer': 'اعتماد وتعديل حركات تحويل المخازن [erp.change_stocktransfer]',
                        'erp.view_repairticket': 'عرض تذاكر الصيانة [erp.view_repairticket]',
                        'erp.add_repairticket': 'إنشاء تذاكر الصيانة الجديدة [erp.add_repairticket]',
                        'erp.change_repairticket': 'تحديث وتعديل تذاكر الصيانة وقطع الغيار [erp.change_repairticket]',
                        'erp.view_cashshift': 'تصفح وإدارة الخزينة والورديات [erp.view_cashshift]',
                        'erp.add_expense': 'تسجيل المصروفات والمنصرف من الوردية [erp.add_expense]',
                        'erp.change_cashshift': 'إغلاق وتسوية الخزينة والورديات [erp.change_cashshift]',
                        'erp.view_stock': 'عرض كميات المخزون والتقارير المالية للمخازن [erp.view_stock]',
                    }
                    perm_desc = [friendly_names.get(p, p) for p in perms]
                    raise PermissionDenied(f"صلاحية مفقودة: {', '.join(perm_desc)}")
            return django_permission_required(perm, login_url=login_url, raise_exception=raise_exception)(view_func)(request, *args, **kwargs)
        return _wrapped_view
    return decorator
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction, models
from django.utils import timezone
from django.contrib import messages
from erp.models import (
    StoreSetting, Contact, Warehouse, Product, Stock, Device, DeviceAttachment,
    PurchaseInvoice, PurchaseItem, StockTransfer, StockTransferItem,
    CashShift, Expense, ExpenseCategory, SaleInvoice, SaleItem, Payment,
    RepairTicket, RepairPartUsed, Warranty, NotificationLog
)
from erp.forms import (
    ContactForm, UsedDeviceForm, DeviceAttachmentFormSet,
    PurchaseInvoiceForm, PurchaseItemFormSet,
    StockTransferForm, StockTransferItemFormSet,
    RepairTicketForm, RepairPartUsedFormSet,
    CashShiftOpenForm, CashShiftCloseForm, ExpenseForm,
    WarehouseForm, SupplierForm, ProductForm, SystemUserCreationForm
)
# ==========================================
# 1. لوحة التحكم (Interactive Dashboard)
# ==========================================
@login_required
def dashboard_view(request):
    # منع المستخدمين غير الإداريين من الوصول للوحة التحكم الرئيسية وتوجيههم لصفحات عملهم
    if not request.user.is_staff and not request.user.is_superuser:
        if request.user.has_perm('erp.add_saleinvoice'):
            return redirect('erp:pos')
        elif request.user.has_perm('erp.change_repairticket'):
            return redirect('erp:repair_list')
        elif request.user.has_perm('erp.view_purchaseinvoice'):
            return redirect('erp:purchase_list')
        else:
            return redirect('erp:pos')
    # إعدادات المحل
    store_setting = StoreSetting.objects.first()
    # حساب الإيرادات الإجمالية
    total_sales = SaleInvoice.objects.aggregate(total=models.Sum('net_amount'))['total'] or 0.00
    # الوردية المفتوحة الحالية للمستخدم
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    active_shift_balance = active_shift.expected_closing_balance if active_shift else 0.00
    # تذاكر الصيانة النشطة
    active_repairs_count = RepairTicket.objects.exclude(status='delivered').count()
    # النواقص (أصناف كميتها في أي مخزن أقل من 5)
    low_stock_items = Stock.objects.filter(quantity__lt=5).select_related('product', 'warehouse')
    # آخر فواتير بيع
    recent_sales = SaleInvoice.objects.order_by('-date_created')[:5].select_related('customer', 'cashier')
    # آخر تذاكر صيانة
    recent_tickets = RepairTicket.objects.order_by('-id')[:5].select_related('customer', 'technician')
    # سجل الإشعارات
    recent_notifications = NotificationLog.objects.order_by('-sent_at')[:5].select_related('customer')
    # البحث السريع بـ QR/الباركود
    search_query = request.GET.get('q', '').strip()
    search_result = None
    if search_query:
        # البحث عن منتج بالباركود
        product = Product.objects.filter(barcode_qr=search_query).first()
        if product:
            # إحضار تفاصيل المخزون والأجهزة
            stocks = Stock.objects.filter(product=product).select_related('warehouse')
            unsold_devices = Device.objects.filter(product=product, is_sold=False).select_related('warehouse')
            search_result = {
                'type': 'product',
                'object': product,
                'stocks': stocks,
                'devices': unsold_devices,
            }
        else:
            # البحث عن جهاز سيريال IMEI
            device = Device.objects.filter(models.Q(imei=search_query) | models.Q(imei2=search_query)).select_related('product', 'warehouse', 'purchased_from').first()
            if device:
                search_result = {
                    'type': 'device',
                    'object': device,
                }
            else:
                messages.warning(request, "لم يتم العثور على أي صنف أو سيريال مطابق.")
    context = {
        'store_setting': store_setting,
        'total_sales': total_sales,
        'active_shift': active_shift,
        'active_shift_balance': active_shift_balance,
        'active_repairs_count': active_repairs_count,
        'low_stock_items': low_stock_items,
        'recent_sales': recent_sales,
        'recent_tickets': recent_tickets,
        'recent_notifications': recent_notifications,
        'search_result': search_result,
        'search_query': search_query,
    }
    return render(request, 'erp/dashboard.html', context)
# ==========================================
# 2. نقطة البيع (Point of Sale - POS)
# ==========================================
@login_required
@permission_required('erp.add_saleinvoice', raise_exception=True)
def pos_view(request):
    # التحقق من وجود وردية مفتوحة للكاشير الحالي
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    if not active_shift:
        messages.warning(request, "يجب فتح وردية جديدة قبل الدخول لشاشة المبيعات.")
        return redirect('erp:shift_manage')
    store_setting = StoreSetting.objects.first()
    # جلب المنتجات والمخازن والعملاء للتفاعل الفوري
    # جلب المنتجات والمخازن والعملاء للتفاعل الفوري
    from django.db.models import Sum, Count, Q, Case, When, Value, IntegerField
    from django.db.models.functions import Coalesce
    products = Product.objects.annotate(
        available_qty=Coalesce(
            Case(
                When(requires_imei=True, then=Count('device', filter=Q(device__is_sold=False))),
                default=Sum('stock__quantity'),
                output_field=IntegerField()
            ),
            Value(0)
        )
    ).filter(available_qty__gt=0)[:12]
    card_list = []
    for prod in products:
        if prod.requires_imei:
            new_qty = prod.device_set.filter(is_sold=False, condition='new').count()
            if new_qty > 0:
                card_list.append({
                    'id': prod.id,
                    'name': f"{prod.name} (جديد)",
                    'barcode_qr': prod.barcode_qr,
                    'product_type': prod.product_type,
                    'get_product_type_display': prod.get_product_type_display(),
                    'selling_price': prod.selling_price,
                    'requires_imei': True,
                    'available_qty': new_qty,
                    'condition': 'new'
                })
            used_qty = prod.device_set.filter(is_sold=False, condition='used').count()
            if used_qty > 0:
                card_list.append({
                    'id': prod.id,
                    'name': f"{prod.name} (مستعمل)",
                    'barcode_qr': prod.barcode_qr,
                    'product_type': prod.product_type,
                    'get_product_type_display': prod.get_product_type_display(),
                    'selling_price': prod.selling_price,
                    'requires_imei': True,
                    'available_qty': used_qty,
                    'condition': 'used'
                })
        else:
            card_list.append({
                'id': prod.id,
                'name': prod.name,
                'barcode_qr': prod.barcode_qr,
                'product_type': prod.product_type,
                'get_product_type_display': prod.get_product_type_display(),
                'selling_price': prod.selling_price,
                'requires_imei': False,
                'available_qty': prod.available_qty,
                'condition': None
            })
    warehouses = Warehouse.objects.filter(is_active=True)
    customers = Contact.objects.filter(contact_type__in=['customer', 'used_seller'])
    warehouse_stocks = Stock.objects.filter(quantity__gt=0).select_related('product', 'warehouse')
    # الأجهزة المتاحة للبيع
    available_devices = Device.objects.filter(is_sold=False).select_related('product', 'warehouse')
    context = {
        'active_shift': active_shift,
        'store_setting': store_setting,
        'products': card_list,
        'warehouses': warehouses,
        'customers': customers,
        'available_devices': available_devices,
        'warehouse_stocks': warehouse_stocks,
    }
    return render(request, 'erp/pos.html', context)
@login_required
def pos_product_search(request):
    """
    مستدعى للبحث السريع عن الباركود أثناء إضافته من قارئ الباركود.
    """
    code = request.GET.get('code', '').strip()
    product = Product.objects.filter(barcode_qr=code).first()
    if not product:
        # البحث في الأجهزة بالسيريال
        device = Device.objects.filter(models.Q(imei=code) | models.Q(imei2=code), is_sold=False).select_related('product', 'warehouse').first()
        if device:
            imei_label = f"{device.imei} / {device.imei2}" if device.imei2 else device.imei
            cond_str = "جديد" if device.condition == 'new' else "مستعمل"
            storage_disp = device.get_storage_display() or ""
            ram_disp = device.get_ram_display() or ""
            specs_list = [s for s in [storage_disp, ram_disp] if s]
            specs_str = f" - {'/'.join(specs_list)}" if specs_list else ""
            return JsonResponse({
                'found': True,
                'is_serialized': True,
                'id': device.product.id,
                'name': f"{device.product.name} (IMEI: {imei_label}) ({cond_str}{specs_str})",
                'product_id': device.product.id,
                'device_id': device.id,
                'imei': imei_label,
                'warehouse_id': device.warehouse.id,
                'price': float(device.product.selling_price),
            })
        return JsonResponse({'found': False})
    return JsonResponse({
        'found': True,
        'is_serialized': product.requires_imei,
        'id': product.id,
        'name': product.name,
        'price': float(product.selling_price),
    })
@login_required
@permission_required('erp.add_saleinvoice', raise_exception=True)
def pos_product_grid(request):
    """
    مستدعى ديناميكياً لتحديث شبكة المنتجات بالبحث و/أو القسم (HTMX AJAX search).
    """
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    from django.db.models import Sum, Count, Q, Case, When, Value, IntegerField
    from django.db.models.functions import Coalesce
    products = Product.objects.annotate(
        available_qty=Coalesce(
            Case(
                When(requires_imei=True, then=Count('device', filter=Q(device__is_sold=False))),
                default=Sum('stock__quantity'),
                output_field=IntegerField()
            ),
            Value(0)
        )
    ).filter(available_qty__gt=0)
    # فلترة بالقسم
    if category:
        products = products.filter(product_type=category)
    # فلترة بكلمة البحث
    if q:
        products = products.filter(models.Q(name__icontains=q) | models.Q(barcode_qr__icontains=q))
    # تحديد العدد بـ 12 صنفاً لأقصى سرعة ممكنة
    products = products[:12]
    card_list = []
    for prod in products:
        if prod.requires_imei:
            new_qty = prod.device_set.filter(is_sold=False, condition='new').count()
            if new_qty > 0:
                card_list.append({
                    'id': prod.id,
                    'name': f"{prod.name} (جديد)",
                    'barcode_qr': prod.barcode_qr,
                    'product_type': prod.product_type,
                    'get_product_type_display': prod.get_product_type_display(),
                    'selling_price': prod.selling_price,
                    'requires_imei': True,
                    'available_qty': new_qty,
                    'condition': 'new'
                })
            used_qty = prod.device_set.filter(is_sold=False, condition='used').count()
            if used_qty > 0:
                card_list.append({
                    'id': prod.id,
                    'name': f"{prod.name} (مستعمل)",
                    'barcode_qr': prod.barcode_qr,
                    'product_type': prod.product_type,
                    'get_product_type_display': prod.get_product_type_display(),
                    'selling_price': prod.selling_price,
                    'requires_imei': True,
                    'available_qty': used_qty,
                    'condition': 'used'
                })
        else:
            card_list.append({
                'id': prod.id,
                'name': prod.name,
                'barcode_qr': prod.barcode_qr,
                'product_type': prod.product_type,
                'get_product_type_display': prod.get_product_type_display(),
                'selling_price': prod.selling_price,
                'requires_imei': False,
                'available_qty': prod.available_qty,
                'condition': None
            })
    return render(request, 'erp/includes/pos_product_cards.html', {'products': card_list})
@login_required
@permission_required('erp.add_saleinvoice', raise_exception=True)
@require_POST
def pos_checkout(request):
    """
    حفظ الفاتورة عبر معاملة قاعدة بيانات متكاملة لضمان موثوقية الخصم والماليات.
    """
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'بيانات غير صالحة'}, status=400)
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    if not active_shift:
        return JsonResponse({'error': 'لا توجد وردية مفتوحة لهذا الكاشير'}, status=400)
    customer_id = data.get('customer_id')
    discount = models.DecimalField().to_python(data.get('discount', 0))
    traded_in_device_id = data.get('traded_in_device_id')
    trade_in_value = models.DecimalField().to_python(data.get('trade_in_value', 0))
    warranty_days = int(data.get('warranty_days', 14))
    items_data = data.get('items', [])
    payments_data = data.get('payments', [])
    if not items_data:
        return JsonResponse({'error': 'لا يمكن حفظ فاتورة خالية من الأصناف'}, status=400)
    try:
        with transaction.atomic():
            customer = get_object_or_404(Contact, id=customer_id)
            # 1. إنشاء رأس الفاتورة
            invoice = SaleInvoice(
                shift=active_shift,
                cashier=request.user,
                customer=customer,
                total_amount=0,  # سيتم حسابه لاحقاً
                discount=discount,
                trade_in_value=trade_in_value,
                net_amount=0
            )
            # ربط جهاز الاستبدال إن وجد
            if traded_in_device_id:
                traded_device = get_object_or_404(Device, id=traded_in_device_id)
                invoice.traded_in_device = traded_device
            invoice.save()
            # 2. إنشاء بنود الفاتورة وحساب الإجمالي
            total_sum = 0
            for item in items_data:
                product_id = item.get('product_id')
                warehouse_id = item.get('warehouse_id')
                device_id = item.get('device_id')
                qty = int(item.get('quantity', 1))
                unit_price = models.DecimalField().to_python(item.get('unit_price', 0))
                product = get_object_or_404(Product, id=product_id)
                warehouse = get_object_or_404(Warehouse, id=warehouse_id)
                sale_item = SaleItem(
                    invoice=invoice,
                    product=product,
                    warehouse=warehouse,
                    quantity=qty,
                    unit_price=unit_price
                )
                if product.requires_imei and device_id:
                    device = get_object_or_404(Device, id=device_id)
                    # التحقق من أن الجهاز ليس مباعاً بالفعل
                    if device.is_sold:
                        raise ValidationError(f"الجهاز بالسيريال {device.imei} مباع بالفعل.")
                    sale_item.device = device
                    sale_item.quantity = 1  # الهاتف المسرين كميته دائماً 1
                sale_item.save()  # سيقوم الـ Signal بخصم المخزن
                total_sum += sale_item.quantity * unit_price
            invoice.total_amount = total_sum
            invoice.net_amount = (total_sum - discount) - trade_in_value
            invoice.save()  # سيقوم الـ Signal الخاص بـ Trade-in بتهيئة الجهاز المستبدل إن وُجد
            # 3. معالجة المدفوعات المتعددة
            total_paid = 0
            for pay in payments_data:
                pay_method = pay.get('payment_method')
                amount = models.DecimalField().to_python(pay.get('amount', 0))
                trans_id = pay.get('transaction_id', '')
                payment = Payment(
                    invoice=invoice,
                    payment_method=pay_method,
                    amount=amount,
                    transaction_id=trans_id
                )
                payment.save()  # سيقوم الـ Signal بإضافة المبالغ النقدية لعهدة الوردية
                total_paid += amount
            # التحقق من تطابق المبلغ المدفوع مع الصافي
            if abs(total_paid - invoice.net_amount) > 0.01:
                raise ValidationError(f"المجموع المدفوع ({total_paid}) لا يتطابق مع صافي الفاتورة ({invoice.net_amount})")
            # 4. تفعيل الضمان التلقائي إن كانت الفاتورة تحتوي على أجهزة مسيرنة
            for item in invoice.items.all():
                if item.product.requires_imei and item.device:
                    Warranty.objects.create(
                        device=item.device,
                        customer=customer,
                        invoice=invoice,
                        duration_days=warranty_days
                    )
            return JsonResponse({'status': 'success', 'invoice_id': invoice.id})
    except ValidationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': f"فشل الحفظ: {str(e)}"}, status=400)
# ==========================================
# 3. شراء الأجهزة المستعملة (Used Device Purchase)
# ==========================================
@login_required
@permission_required('erp.add_device', raise_exception=True)
def used_device_purchase(request):
    store_setting = StoreSetting.objects.first()
    if request.method == 'POST':
        contact_form = ContactForm(request.POST)
        device_form = UsedDeviceForm(request.POST)
        attachment_formset = DeviceAttachmentFormSet(request.POST, request.FILES)
        # نتحقق من وجود بائع مسجل مسبقاً برقم الهاتف لتجنب التكرار
        phone = request.POST.get('phone', '').strip()
        seller = None
        if phone:
            seller = Contact.objects.filter(phone=phone).first()
        if seller:
            contact_form = ContactForm(request.POST, instance=seller)
        # تحقق من تكرار السيريال/IMEI لتنبيه المستخدم وفتح تقرير
        imei = request.POST.get('imei', '').strip()
        imei2 = request.POST.get('imei2', '').strip()
        existing_device = None
        if imei:
            existing_device = Device.objects.filter(models.Q(imei=imei) | models.Q(imei2=imei)).first()
        if not existing_device and imei2:
            existing_device = Device.objects.filter(models.Q(imei=imei2) | models.Q(imei2=imei2)).first()
        if existing_device:
            from django.urls import reverse
            history_url = reverse('erp:device_history', args=[existing_device.pk])
            messages.error(
                request,
                f"تنبيه: يوجد جهاز بالفعل مسجل بهذا السيريال ({existing_device.imei})! "
                f"<a href='{history_url}' class='btn btn-warning btn-sm ms-2 fw-bold'><i class='bi bi-clock-history'></i> عرض تقرير تاريخ هذا الجهاز</a>"
            )
            context = {
                'store_setting': store_setting,
                'contact_form': contact_form,
                'device_form': device_form,
                'attachment_formset': attachment_formset,
            }
            return render(request, 'erp/used_purchase.html', context)
        if contact_form.is_valid() and device_form.is_valid():
            try:
                with transaction.atomic():
                    # حفظ بيانات البائع والتأكد من أنه بائع أجهزة مستعملة
                    seller_instance = contact_form.save(commit=False)
                    seller_instance.contact_type = 'used_seller'
                    seller_instance.save()
                    # حفظ بيانات الجهاز
                    device_instance = device_form.save(commit=False)
                    device_instance.purchased_from = seller_instance
                    device_instance.condition = 'used'
                    device_instance.is_sold = False
                    device_instance.save()
                    # حفظ المرفقات والأوراق الرسمية بعد ربطها بالجهاز المنشأ
                    attachment_formset.instance = device_instance
                    if attachment_formset.is_valid():
                        attachment_formset.save()
                    else:
                        raise ValidationError("بيانات المرفقات غير صالحة.")
                    messages.success(request, f"تم تسجيل شراء الجهاز المستعمل {device_instance.imei} بنجاح.")
                    return redirect('erp:dashboard')
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
        else:
            errors = []
            for field, err_list in contact_form.errors.items():
                label = contact_form.fields[field].label or field
                errors.append(f"• {label}: {', '.join(err_list)}")
            for field, err_list in device_form.errors.items():
                label = device_form.fields[field].label or field
                errors.append(f"• {label}: {', '.join(err_list)}")
            for form in attachment_formset:
                if form.errors:
                    for field, err_list in form.errors.items():
                        label = form.fields[field].label or field
                        errors.append(f"• المرفق - {label}: {', '.join(err_list)}")
            if errors:
                error_msg = "يرجى تصحيح الأخطاء التالية:\n" + "\n".join(errors)
                messages.error(request, error_msg)
            else:
                messages.error(request, "يرجى التحقق من صحة الحقول المدخلة.")
    else:
        contact_form = ContactForm(initial={'contact_type': 'used_seller'})
        device_form = UsedDeviceForm()
        attachment_formset = DeviceAttachmentFormSet()
    context = {
        'store_setting': store_setting,
        'contact_form': contact_form,
        'device_form': device_form,
        'attachment_formset': attachment_formset,
    }
    return render(request, 'erp/used_purchase.html', context)
@login_required
@permission_required('erp.add_device', raise_exception=True)
def quick_add_product(request):
    """
    إضافة موديل هاتف جديد بسرعة من شاشة شراء المستعمل.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            barcode_qr = data.get('barcode_qr', '').strip()
            selling_price = data.get('selling_price', '0')
            if not name or not barcode_qr or not selling_price:
                return JsonResponse({'error': 'يرجى ملء جميع الحقول المطلوبة (الاسم، الباركود، سعر البيع).'}, status=400)
            if Product.objects.filter(barcode_qr=barcode_qr).exists():
                return JsonResponse({'error': 'هذا الباركود مسجل لموديل آخر بالفعل.'}, status=400)
            product = Product.objects.create(
                name=name,
                barcode_qr=barcode_qr,
                product_type='phone',
                selling_price=models.DecimalField(max_digits=10, decimal_places=2).to_python(selling_price),
                requires_imei=True,
                average_cost=0.00
            )
            return JsonResponse({
                'status': 'success',
                'id': product.id,
                'name': product.name
            })
        except Exception as e:
            return JsonResponse({'error': f"فشل الحفظ: {str(e)}"}, status=400)
    return JsonResponse({'error': 'طريقة طلب غير صالحة.'}, status=405)
@login_required
def product_name_search(request):
    """
    البحث الفوري عن المنتجات بالاسم أو الباركود لمنع التكرار.
    """
    query = request.GET.get('q', '').strip()
    all_types = request.GET.get('all_types', 'false').lower() == 'true'
    if len(query) < 2:
        return JsonResponse({'products': []})
    # فلترة المنتجات بالاسم أو الباركود
    q_filter = models.Q(name__icontains=query) | models.Q(barcode_qr__icontains=query)
    if not all_types:
        products = Product.objects.filter(q_filter, product_type='phone')[:10]
    else:
        products = Product.objects.filter(q_filter)[:10]
    results = []
    for p in products:
        results.append({
            'id': p.id,
            'name': p.name,
            'barcode_qr': p.barcode_qr,
            'selling_price': float(p.selling_price)
        })
    return JsonResponse({'products': results})
# ==========================================
# 4. المشتريات (Purchase Invoices)
# ==========================================
@login_required
@permission_required('erp.view_purchaseinvoice', raise_exception=True)
def purchase_invoice_list(request):
    purchases = PurchaseInvoice.objects.all().order_by('-invoice_date').select_related('supplier', 'created_by')
    return render(request, 'erp/purchase_list.html', {'purchases': purchases})
@login_required
@permission_required('erp.add_purchaseinvoice', raise_exception=True)
def purchase_invoice_create(request):
    store_setting = StoreSetting.objects.first()
    if request.method == 'POST':
        invoice_form = PurchaseInvoiceForm(request.POST)
        formset = PurchaseItemFormSet(request.POST)
        if invoice_form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # حفظ رأس الفاتورة
                    invoice = invoice_form.save(commit=False)
                    invoice.created_by = request.user
                    # تعقيم وحساب المبالغ المدفوعة بناءً على طريقة الدفع
                    if invoice.payment_method == 'cash':
                        invoice.paid_amount = invoice.net_amount
                    elif invoice.payment_method == 'credit':
                        invoice.paid_amount = 0
                    elif invoice.payment_method == 'partial':
                        if invoice.paid_amount > invoice.net_amount:
                            invoice.paid_amount = invoice.net_amount
                        elif invoice.paid_amount < 0:
                            invoice.paid_amount = 0
                    invoice.save()
                    # حفظ البنود وتحديث المخزون ومتوسط التكلفة تلقائياً بواسطة السجنل
                    formset.instance = invoice
                    formset.save()
                    messages.success(request, "تم تسجيل فاتورة المشتريات وإدخال البضاعة للمخازن بنجاح.")
                    return redirect('erp:purchase_list')
            except Exception as e:
                messages.error(request, f"حدث خطأ في الحفظ: {str(e)}")
        else:
            messages.error(request, "يرجى مراجعة الحقول وإدخال البنود بشكل صحيح.")
    else:
        invoice_form = PurchaseInvoiceForm()
        formset = PurchaseItemFormSet()
    context = {
        'store_setting': store_setting,
        'invoice_form': invoice_form,
        'formset': formset,
        'products_require_imei': list(Product.objects.filter(requires_imei=True).values_list('id', flat=True)),
    }
    return render(request, 'erp/purchase_create.html', context)
@login_required
@permission_required('erp.view_purchaseinvoice', raise_exception=True)
def purchase_invoice_detail(request, pk):
    """
    عرض تفاصيل فاتورة الشراء من الموردين.
    """
    invoice = get_object_or_404(PurchaseInvoice, pk=pk)
    items = invoice.items.all().select_related('product', 'warehouse')
    store_setting = StoreSetting.objects.first()
    # تفكيك السيريالات وعرضها بشكل مرتب إذا وجد
    for item in items:
        if item.product.requires_imei and item.imei_list:
            item.imeis = [imei.strip() for imei in item.imei_list.split(',') if imei.strip()]
    context = {
        'invoice': invoice,
        'items': items,
        'store_setting': store_setting,
    }
    return render(request, 'erp/purchase_invoice_detail.html', context)
# ==========================================
# 5. حركة تحويل المخازن (Stock Transfers)
# ==========================================
@login_required
@permission_required('erp.view_stocktransfer', raise_exception=True)
def transfer_list(request):
    transfers = StockTransfer.objects.all().order_by('-created_at').select_related('from_warehouse', 'to_warehouse', 'created_by')
    return render(request, 'erp/transfer_list.html', {'transfers': transfers})
@login_required
@permission_required('erp.add_stocktransfer', raise_exception=True)
def transfer_create(request):
    if request.method == 'POST':
        form = StockTransferForm(request.POST)
        formset = StockTransferItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    transfer = form.save(commit=False)
                    transfer.created_by = request.user
                    transfer.save()
                    formset.instance = transfer
                    formset.save()
                    messages.success(request, "تم تسجيل طلب تحويل البضاعة.")
                    return redirect('erp:transfer_list')
            except Exception as e:
                messages.error(request, f"فشل الحفظ: {str(e)}")
    else:
        form = StockTransferForm()
        formset = StockTransferItemFormSet()
    # Build a dictionary of warehouse stock data
    warehouse_data = {}
    for wh in Warehouse.objects.filter(is_active=True):
        wh_id = str(wh.id)
        warehouse_data[wh_id] = {
            'products': [],
            'devices': {}  # product_id -> list of devices
        }
        # 1. Non-IMEI stock
        stocks = Stock.objects.filter(warehouse=wh, quantity__gt=0).select_related('product')
        for st in stocks:
            if not st.product.requires_imei:
                warehouse_data[wh_id]['products'].append({
                    'id': st.product.id,
                    'name': st.product.name,
                    'requires_imei': False,
                    'available_qty': st.quantity
                })
        # 2. IMEI Devices
        devices = Device.objects.filter(warehouse=wh, is_sold=False).select_related('product')
        device_groups = {}
        for dev in devices:
            prod_id = dev.product.id
            if prod_id not in device_groups:
                device_groups[prod_id] = []
            cond_display = "جديد" if dev.condition == 'new' else "مستعمل"
            display_name = f"{dev.imei}"
            if dev.imei2:
                display_name += f" / {dev.imei2}"
            display_name += f" ({cond_display})"
            device_groups[prod_id].append({
                'id': dev.id,
                'display': display_name
            })
        if device_groups:
            products_map = {p.id: p for p in Product.objects.filter(id__in=device_groups.keys())}
            for prod_id, dev_list in device_groups.items():
                product_obj = products_map.get(prod_id)
                if product_obj:
                    warehouse_data[wh_id]['products'].append({
                        'id': prod_id,
                        'name': product_obj.name,
                        'requires_imei': True,
                        'available_qty': len(dev_list)
                    })
                    warehouse_data[wh_id]['devices'][str(prod_id)] = dev_list
    warehouse_stock_json = json.dumps(warehouse_data)
    return render(request, 'erp/transfer_create.html', {
        'form': form,
        'formset': formset,
        'warehouse_stock_json': warehouse_stock_json
    })
@login_required
@permission_required('erp.change_stocktransfer', raise_exception=True)
def transfer_complete(request, pk):
    """
    تأكيد استلام الشحنة وتحديث مواقع المخازن وتفعيل السجنل.
    """
    transfer = get_object_or_404(StockTransfer, pk=pk)
    if transfer.status == 'pending':
        transfer.status = 'completed'
        transfer.save()  # سيقوم الـ pre_save بنقل البضائع للأجهزة والأصناف
        messages.success(request, f"تم تأكيد استلام الشحنة #{transfer.id} بنجاح.")
    else:
        messages.warning(request, "هذه الحركة مستلمة ومغلقة مسبقاً.")
    return redirect('erp:transfer_list')
# ==========================================
# 6. الصيانة وتذاكر التصليح (Maintenance Cycle)
# ==========================================
@login_required
@permission_required('erp.view_repairticket', raise_exception=True)
def repair_ticket_list(request):
    # إحضار كافة التذاكر مع التحميل المسبق لتجنب N+1 Queries
    tickets = RepairTicket.objects.all().order_by('-id').select_related('customer', 'technician')
    parts = Product.objects.filter(product_type='spare_part')
    warehouses = Warehouse.objects.filter(is_active=True)
    from django.contrib.auth.models import User
    technicians = User.objects.filter(groups__name='فني الصيانة')
    context = {
        'tickets': tickets,
        'parts': parts,
        'warehouses': warehouses,
        'technicians': technicians,
    }
    return render(request, 'erp/repairs.html', context)
@login_required
@permission_required('erp.add_repairticket', raise_exception=True)
def repair_ticket_create(request):
    if request.method == 'POST':
        form = RepairTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save()
            messages.success(request, f"تم فتح تذكرة الصيانة #{ticket.id} بنجاح.")
            return redirect('erp:repair_list')
    else:
        form = RepairTicketForm()
    return render(request, 'erp/repair_create.html', {'form': form})
@login_required
@permission_required('erp.change_repairticket', raise_exception=True)
@require_POST
def repair_add_part(request, pk):
    """
    إضافة قطع غيار للتذكرة وخصمها من المخزن عبر سجنل RepairPartUsed.
    """
    ticket = get_object_or_404(RepairTicket, pk=pk)
    product_id = request.POST.get('product_id')
    warehouse_id = request.POST.get('warehouse_id')
    qty = int(request.POST.get('quantity', 1))
    price = models.DecimalField().to_python(request.POST.get('price', 0))
    product = get_object_or_404(Product, id=product_id)
    warehouse = get_object_or_404(Warehouse, id=warehouse_id)
    # التحقق من توفر المخزون للبضائع السائبة
    if not product.requires_imei:
        stock = Stock.objects.filter(product=product, warehouse=warehouse).first()
        if not stock or stock.quantity < qty:
            return JsonResponse({'error': 'المخزون غير كافٍ لصرف قطعة الغيار هذه'}, status=400)
    part_used = RepairPartUsed.objects.create(
        ticket=ticket,
        product=product,
        warehouse=warehouse,
        quantity=qty,
        price=price
    )
    # إرسال رسالة واتساب وهمية للعميل
    msg = f"مرحباً {ticket.customer.name}، تم تركيب {product.name} لجهازك {ticket.device_model} بسعر {price} ج.م."
    NotificationLog.objects.create(
        customer=ticket.customer,
        ticket=ticket,
        notification_type='whatsapp',
        message_body=msg
    )
    return JsonResponse({
        'status': 'success',
        'part_id': part_used.id,
        'product_name': product.name,
        'quantity': qty,
        'price': float(price)
    })
@login_required
@permission_required('erp.change_repairticket', raise_exception=True)
@require_POST
def repair_change_status(request, pk):
    """
    تعديل حالة الصيانة وإرسال إشعار فوري وتلقائي للعميل.
    """
    ticket = get_object_or_404(RepairTicket, pk=pk)
    new_status = request.POST.get('status')
    if new_status in dict(RepairTicket.STATUS_CHOICES):
        ticket.status = new_status
        ticket.save()
        # إرسال إشعار تلقائي للعميل بناءً على تغيير الحالة
        status_display = ticket.get_status_display()
        msg = f"عزيزي العميل، تم تعديل حالة إصلاح جهازك {ticket.device_model} إلى ({status_display})."
        NotificationLog.objects.create(
            customer=ticket.customer,
            ticket=ticket,
            notification_type='whatsapp',
            message_body=msg
        )
        return JsonResponse({'status': 'success', 'new_status_display': status_display})
    return JsonResponse({'error': 'حالة غير صالحة'}, status=400)
@login_required
@permission_required('erp.change_repairticket', raise_exception=True)
@require_POST
def repair_ticket_edit(request, pk):
    """
    تحديث بيانات التذكرة (المصنعية، حالة التذكرة، وصف العطل، الفني المسؤول).
    """
    ticket = get_object_or_404(RepairTicket, pk=pk)
    labor_cost = request.POST.get('labor_cost')
    issue_description = request.POST.get('issue_description')
    technician_id = request.POST.get('technician_id')
    status = request.POST.get('status')
    try:
        if labor_cost is not None:
            ticket.labor_cost = models.DecimalField(max_digits=10, decimal_places=2).to_python(labor_cost)
        if issue_description is not None:
            ticket.issue_description = issue_description.strip()
        if status in dict(RepairTicket.STATUS_CHOICES):
            if ticket.status != status:
                ticket.status = status
                # إرسال إشعار تلقائي للعميل بمناسبة تغيير الحالة
                status_display = ticket.get_status_display()
                msg = f"عزيزي العميل، تم تعديل حالة إصلاح جهازك {ticket.device_model} إلى ({status_display})."
                NotificationLog.objects.create(
                    customer=ticket.customer,
                    ticket=ticket,
                    notification_type='whatsapp',
                    message_body=msg
                )
        if technician_id:
            from django.contrib.auth.models import User
            technician = get_object_or_404(User, id=technician_id)
            ticket.technician = technician
        else:
            ticket.technician = None
        ticket.save()
        messages.success(request, f"تم تعديل تذكرة الصيانة #{ticket.id} بنجاح.")
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': f"فشل الحفظ: {str(e)}"}, status=400)
# ==========================================
# 7. إدارة الخزينة والورديات (Cash Shifts)
# ==========================================
@login_required
@permission_required('erp.view_cashshift', raise_exception=True)
def shift_manage_view(request):
    # الوردية المفتوحة الحالية للكاشير
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    if active_shift:
        # إحضار المصاريف والعمليات التابعة للوردية الحالية
        expenses = active_shift.expenses.all().select_related('category')
        sales = SaleInvoice.objects.filter(shift=active_shift).select_related('customer')
        # حساب إجمالي المبيعات الكاش
        cash_sales = Payment.objects.filter(
            invoice__shift=active_shift,
            payment_method='cash'
        ).aggregate(total=models.Sum('amount'))['total'] or 0.00
        # حساب إجمالي المبيعات فيزا ومحفظة
        visa_sales = Payment.objects.filter(
            invoice__shift=active_shift,
            payment_method='visa'
        ).aggregate(total=models.Sum('amount'))['total'] or 0.00
        wallet_sales = Payment.objects.filter(
            invoice__shift=active_shift,
            payment_method='wallet'
        ).aggregate(total=models.Sum('amount'))['total'] or 0.00
        expense_form = ExpenseForm()
        close_form = CashShiftCloseForm(instance=active_shift)
        context = {
            'active_shift': active_shift,
            'expenses': expenses,
            'sales': sales,
            'cash_sales': cash_sales,
            'visa_sales': visa_sales,
            'wallet_sales': wallet_sales,
            'expense_form': expense_form,
            'close_form': close_form,
        }
        return render(request, 'erp/shift_detail.html', context)
    else:
        # شاشة فتح وردية جديدة
        if request.method == 'POST':
            # التحقق الإضافي لمنع فتح أكثر من وردية لنفس الكاشير
            already_open = CashShift.objects.filter(cashier=request.user, status='open').exists()
            if already_open:
                messages.error(request, "خطأ: لديك وردية مفتوحة بالفعل. لا يمكن فتح وردية جديدة قبل إغلاق الوردية الحالية.")
                return redirect('erp:shift_manage')
            form = CashShiftOpenForm(request.POST)
            if form.is_valid():
                shift = form.save(commit=False)
                shift.cashier = request.user
                shift.status = 'open'
                shift.save()
                messages.success(request, "تم فتح الوردية بنجاح. يومك مبارك ورزقك واسع!")
                return redirect('erp:dashboard')
        else:
            form = CashShiftOpenForm()
        return render(request, 'erp/shift_open.html', {'form': form})
@login_required
@permission_required('erp.add_expense', raise_exception=True)
@require_POST
def shift_add_expense(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'غير مسموح للكاشير بتسجيل مصروفات'}, status=403)
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    if not active_shift:
        return JsonResponse({'error': 'لا توجد وردية مفتوحة لتسجيل المصاريف'}, status=400)
    form = ExpenseForm(request.POST)
    if form.is_valid():
        expense = form.save(commit=False)
        expense.shift = active_shift
        expense.save() # سيقوم الـ Signal بإعادة حساب الوردية تلقائياً
        return JsonResponse({
            'status': 'success',
            'amount': float(expense.amount),
            'category': expense.category.name,
            'description': expense.description
        })
    return JsonResponse({'error': 'بيانات غير صالحة'}, status=400)
@login_required
@permission_required('erp.change_cashshift', raise_exception=True)
@require_POST
def shift_close(request):
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    if not active_shift:
        messages.error(request, "لا توجد وردية مفتوحة لإغلاقها.")
        return redirect('erp:shift_manage')
    form = CashShiftCloseForm(request.POST, instance=active_shift)
    if form.is_valid():
        shift = form.save(commit=False)
        shift.status = 'closed'
        shift.end_time = timezone.now()
        shift.save() # سيقوم الـ pre_save بتحديث expected_closing_balance للمرة الأخيرة
        discrepancy = shift.actual_cash - shift.expected_closing_balance
        if discrepancy == 0:
            messages.success(request, "تم إغلاق الوردية وتصفيتها بنجاح بدون أي فروقات.")
        elif discrepancy > 0:
            messages.warning(request, f"تم إغلاق الوردية بوجود فائض قدره {discrepancy} ج.م.")
        else:
            messages.error(request, f"تم إغلاق الوردية بوجود عجز قدره {abs(discrepancy)} ج.م.")
        return redirect('erp:dashboard')
    messages.error(request, "حدث خطأ أثناء محاولة إغلاق الوردية.")
    return redirect('erp:shift_manage')
@login_required
def device_history(request, pk):
    device = get_object_or_404(Device, pk=pk)
    # 1. تفاصيل الشراء (جديد من مورد)
    purchase_invoice = None
    purchase_item = None
    if device.purchased_from and device.purchased_from.contact_type == 'supplier':
        items = PurchaseItem.objects.filter(product=device.product)
        for item in items:
            if item.imei_list:
                imeis = [i.strip() for i in item.imei_list.replace('/', ',').split(',') if i.strip()]
                if device.imei in imeis or (device.imei2 and device.imei2 in imeis):
                    purchase_item = item
                    purchase_invoice = item.invoice
                    break
    # 2. تفاصيل البيع
    sale_item = SaleItem.objects.filter(device=device).first()
    sale_invoice = sale_item.invoice if sale_item else None
    # 3. تفاصيل الاستبدال (إذا دخل المحل كجهاز مستبدل Trade-in)
    traded_in_invoice = SaleInvoice.objects.filter(traded_in_device=device).first()
    # 4. تفاصيل حركات النقل بين الفروع/المستودعات
    transfers = StockTransferItem.objects.filter(device=device).select_related('transfer')
    # 5. تفاصيل الصيانة والتصليح المرتبطة بهذا السيريال
    repairs = RepairTicket.objects.filter(
        models.Q(device_imei=device.imei) |
        (models.Q(device_imei=device.imei2) if device.imei2 else models.Q(id=-1))
    ).order_by('-id')
    store_setting = StoreSetting.objects.first()
    context = {
        'store_setting': store_setting,
        'device': device,
        'purchase_invoice': purchase_invoice,
        'purchase_item': purchase_item,
        'sale_invoice': sale_invoice,
        'sale_item': sale_item,
        'traded_in_invoice': traded_in_invoice,
        'transfers': transfers,
        'repairs': repairs,
    }
    return render(request, 'erp/device_history.html', context)
@login_required
def setup_dashboard_view(request):
    # تقييد الوصول بناءً على الصلاحية الإدارية للتهيئة
    if not (request.user.has_perm('erp.change_storesetting') or request.user.is_superuser):
        messages.error(request, "غير مسموح لك بالوصول لصفحة الإعدادات والتهيئة.")
        # توجيه المستخدم لصفحة عمله المخصصة
        if request.user.has_perm('erp.add_saleinvoice'):
            return redirect('erp:pos')
        elif request.user.has_perm('erp.change_repairticket'):
            return redirect('erp:repair_list')
        else:
            return redirect('erp:pos')
    from django.contrib.auth.models import User, Group
    # تهيئة النماذج الفارغة بشكل افتراضي للعرض
    warehouse_form = WarehouseForm()
    supplier_form = SupplierForm()
    product_form = ProductForm()
    user_form = SystemUserCreationForm()
    # معالجة طلبات الإدخال (POST)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_warehouse':
            form = WarehouseForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "تم تسجيل الفرع/المخزن الجديد بنجاح.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات المخزن.")
                warehouse_form = form # احتفاظ بالنموذج غير الصالح لعرض الأخطاء
        elif action == 'add_supplier':
            form = SupplierForm(request.POST)
            if form.is_valid():
                supplier = form.save(commit=False)
                supplier.contact_type = 'supplier' # تعيين جهة الاتصال كمورد
                supplier.save()
                messages.success(request, "تم تسجيل المورد الجديد بنجاح.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات المورد.")
                supplier_form = form # احتفاظ بالنموذج غير الصالح لعرض الأخطاء
        elif action == 'add_product':
            form = ProductForm(request.POST)
            if form.is_valid():
                # التحقق من تكرار الباركود
                barcode = form.cleaned_data.get('barcode_qr')
                if barcode and Product.objects.filter(barcode_qr=barcode).exists():
                    messages.error(request, "خطأ: هذا الباركود مسجل مسبقاً لصنف آخر.")
                    product_form = form # احتفاظ بالنموذج غير الصالح
                else:
                    form.save()
                    messages.success(request, "تم تسجيل الصنف الجديد بالدليل بنجاح.")
                    return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات الصنف.")
                product_form = form # احتفاظ بالنموذج غير الصالح لعرض الأخطاء
        elif action == 'add_user':
            form = SystemUserCreationForm(request.POST)
            if form.is_valid():
                username = form.cleaned_data.get('username')
                first_name = form.cleaned_data.get('first_name')
                last_name = form.cleaned_data.get('last_name')
                email = form.cleaned_data.get('email')
                password = form.cleaned_data.get('password')
                role = form.cleaned_data.get('role')
                # إنشاء المستخدم
                new_user = User.objects.create_user(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password
                )
                # ربط بالمجموعة (إنشاء المجموعة تلقائياً إذا لم تكن موجودة بقاعدة البيانات)
                group, _ = Group.objects.get_or_create(name=role)
                new_user.groups.add(group)
                # إذا كان المدير العام، نمنحه رتبة إداري (is_staff) لتصفح لوحات النظام والتهيئة
                if role == 'المدير العام':
                    new_user.is_staff = True
                    new_user.save()
                messages.success(request, f"تم تسجيل المستخدم الجديد '{username}' بنجاح وتعيينه لدور '{role}'.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات المستخدم الجديد.")
                user_form = form # احتفاظ بالنموذج لعرض الأخطاء
    # جلب قوائم البيانات الحالية
    warehouses = Warehouse.objects.all().order_by('id')
    suppliers = Contact.objects.filter(contact_type='supplier').order_by('-id')
    products = Product.objects.all().order_by('-id')
    users = User.objects.filter(is_superuser=False).prefetch_related('groups').order_by('-id')
    context = {
        'warehouse_form': warehouse_form,
        'supplier_form': supplier_form,
        'product_form': product_form,
        'user_form': user_form,
        'warehouses': warehouses,
        'suppliers': suppliers,
        'products': products,
        'users': users,
    }
    return render(request, 'erp/setup.html', context)
# ==========================================
# 8. تفاصيل الفواتير وتذاكر الصيانة (Details Views)
# ==========================================
@login_required
def sale_invoice_detail(request, pk):
    """
    عرض تفاصيل فاتورة بيع مع خيار الطباعة
    """
    from django.core.exceptions import PermissionDenied
    invoice = get_object_or_404(SaleInvoice, pk=pk)
    # التحقق من الصلاحيات
    if not (request.user.is_staff or request.user.is_superuser or 
            request.user.has_perm('erp.view_saleinvoice') or 
            request.user.has_perm('erp.add_saleinvoice')):
        raise PermissionDenied("ليس لديك صلاحية لعرض هذه الفاتورة.")
    items = invoice.items.all().select_related('product', 'warehouse', 'device')
    payments = invoice.payments.all()
    warranties = Warranty.objects.filter(invoice=invoice)
    store_setting = StoreSetting.objects.first()
    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'warranties': warranties,
        'store_setting': store_setting,
    }
    return render(request, 'erp/sale_invoice_detail.html', context)
@login_required
def repair_ticket_detail(request, pk):
    """
    عرض تفاصيل تذكرة الصيانة وحالتها وقطع الغيار وسجل التنبيهات
    """
    from django.core.exceptions import PermissionDenied
    ticket = get_object_or_404(RepairTicket, pk=pk)
    # التحقق من الصلاحيات
    if not (request.user.is_staff or request.user.is_superuser or 
            request.user.has_perm('erp.view_repairticket') or 
            request.user.has_perm('erp.change_repairticket')):
        raise PermissionDenied("ليس لديك صلاحية لعرض هذه التذكرة.")
    parts_used = ticket.parts_used.all().select_related('product', 'warehouse')
    notifications = ticket.notificationlog_set.all().order_by('-sent_at')
    store_setting = StoreSetting.objects.first()
    # حساب إجمالي التكاليف
    parts_cost = sum(part.quantity * part.price for part in parts_used)
    total_cost = ticket.labor_cost + parts_cost
    context = {
        'ticket': ticket,
        'parts_used': parts_used,
        'notifications': notifications,
        'store_setting': store_setting,
        'parts_cost': parts_cost,
        'total_cost': total_cost,
    }
    return render(request, 'erp/repair_ticket_detail.html', context)
@login_required
def inventory_dashboard(request):
    """
    لوحة إدارة المخزون والمستودعات وعرض تفاصيل البضائع والأجهزة المتوفرة
    """
    from django.core.exceptions import PermissionDenied
    # التحقق من الصلاحية
    if not (request.user.is_staff or request.user.is_superuser or 
            request.user.has_perm('erp.view_stock') or 
            request.user.has_perm('erp.view_device')):
        raise PermissionDenied("ليس لديك صلاحية لعرض لوحة المخزون.")
    store_setting = StoreSetting.objects.first()
    warehouses = Warehouse.objects.filter(is_active=True).order_by('id')
    # استخراج الفلاتر والبحث
    warehouse_id = request.GET.get('warehouse')
    product_type = request.GET.get('type')
    search_query = request.GET.get('q', '').strip()
    # 1. المخزون السائب (Bulk Stock)
    stock_qs = Stock.objects.all().select_related('product', 'warehouse')
    # 2. الأجهزة المسيرنة غير المباعة (Serialized Devices in Stock)
    device_qs = Device.objects.filter(is_sold=False).select_related('product', 'warehouse')
    # تطبيق فلتر المستودع
    if warehouse_id:
        stock_qs = stock_qs.filter(warehouse_id=warehouse_id)
        device_qs = device_qs.filter(warehouse_id=warehouse_id)
    # تطبيق فلتر نوع الصنف (للبضائع السائبة فقط)
    if product_type:
        stock_qs = stock_qs.filter(product__product_type=product_type)
        if product_type != 'phone':
            device_qs = device_qs.none()
    # تطبيق فلتر البحث بالكلمة أو الباركود أو السيريال
    if search_query:
        # البحث في البضائع السائبة باسم الصنف أو الباركود
        stock_qs = stock_qs.filter(
            models.Q(product__name__icontains=search_query) |
            models.Q(product__barcode_qr__icontains=search_query)
        )
        # البحث في الأجهزة باسم الموديل أو الباركود أو السيريال
        device_qs = device_qs.filter(
            models.Q(product__name__icontains=search_query) |
            models.Q(product__barcode_qr__icontains=search_query) |
            models.Q(imei__icontains=search_query) |
            models.Q(imei2__icontains=search_query)
        )
    # جلب القوائم النهائية
    bulk_stock = stock_qs.order_by('-quantity')
    devices = device_qs.order_by('-id')
    # حساب الإحصائيات (KPIs)
    total_bulk_qty = sum(item.quantity for item in bulk_stock)
    total_devices_qty = devices.count()
    # حساب القيم المالية الإجمالية
    total_bulk_cost = sum(item.quantity * (item.product.average_cost or 0) for item in bulk_stock)
    total_device_cost = sum(device.cost or 0 for device in devices)
    total_cost_valuation = total_bulk_cost + total_device_cost
    total_bulk_selling = sum(item.quantity * (item.product.selling_price or 0) for item in bulk_stock)
    total_device_selling = sum(device.product.selling_price or 0 for device in devices)
    total_selling_valuation = total_bulk_selling + total_device_selling
    context = {
        'store_setting': store_setting,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
        'selected_type': product_type,
        'search_query': search_query,
        'bulk_stock': bulk_stock,
        'devices': devices,
        'total_bulk_qty': total_bulk_qty,
        'total_devices_qty': total_devices_qty,
        'total_cost_valuation': total_cost_valuation,
        'total_selling_valuation': total_selling_valuation,
    }
    return render(request, 'erp/inventory.html', context)
@login_required
def ajax_create_customer(request):
    """
    إنشاء عميل جديد عبر AJAX وإعادته كـ JSON.
    """
    if request.method == 'POST':
        import json
        from django.http import JsonResponse
        from erp.forms import ContactForm
        # دعم كل من JSON أو POST التقليدي
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except ValueError:
                return JsonResponse({'status': 'error', 'message': 'بيانات JSON غير صالحة.'}, status=400)
        else:
            data = request.POST
        post_data = {
            'name': data.get('name', '').strip(),
            'phone': data.get('phone', '').strip(),
            'national_id': data.get('national_id', '').strip() or None,
            'address': data.get('address', '').strip() or None,
        }
        form = ContactForm(post_data)
        if form.is_valid():
            try:
                contact = form.save(commit=False)
                contact.contact_type = 'customer'
                contact.save()
                return JsonResponse({
                    'status': 'success',
                    'customer': {
                        'id': contact.id,
                        'name': contact.name,
                        'phone': contact.phone
                    }
                })
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'فشل الحفظ: {str(e)}'})
        else:
            errors = {}
            for field, errs in form.errors.items():
                errors[field] = errs[0]
            return JsonResponse({'status': 'error', 'errors': errors})
    from django.http import JsonResponse
    return JsonResponse({'status': 'error', 'message': 'طريقة الطلب غير مسموح بها.'}, status=405)
def custom_permission_denied_view(request, exception=None):
    """
    عرض مخصص لخطأ 403 - وصول غير مصرح به مع إظهار الصلاحية المفقودة
    """
    message = str(exception) if exception else "عذراً، لا تمتلك الصلاحية الكافية للوصول لهذه الصفحة."
    context = {
        'message': message,
        'title': 'خطأ 403 - غير مسموح'
    }
    return render(request, 'erp/403.html', context, status=403)
@login_required
def reports_dashboard(request):
    # Enforce staff/superuser restrictions
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied("عذراً، يجب أن تكون مشرفاً أو مديراً للوصول لصفحة التقارير.")
    from decimal import Decimal
    from django.db import models
    from django.utils import timezone
    from datetime import datetime, timedelta
    from erp.models import (
        Warehouse, Product, Stock, Device, PurchaseInvoice, PurchaseItem,
        SaleInvoice, SaleItem, Payment, RepairTicket, RepairPartUsed, Expense, Contact
    )
    # 1. Parse Date Range Filters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    # Defaults: Last 30 days
    today = timezone.localtime(timezone.now()).date()
    default_start = today - timedelta(days=30)
    default_end = today
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = default_start
    else:
        start_date = default_start
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = default_end
    else:
        end_date = default_end
    # Make datetime boundaries for querying
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
    # ==========================================
    # 1. FINANCIAL REPORTS (التقارير المالية)
    # ==========================================
    # A. Profit & Loss Calculations
    sales_in_period = SaleInvoice.objects.filter(date_created__range=(start_dt, end_dt))
    total_sales_revenue = sales_in_period.aggregate(total=models.Sum('net_amount'))['total'] or Decimal('0.00')
    sales_list = sales_in_period.select_related('customer', 'cashier').order_by('-date_created')
    cogs_serialized = Decimal('0.00')
    cogs_bulk = Decimal('0.00')
    cogs_list = []
    sale_items = SaleItem.objects.filter(invoice__date_created__range=(start_dt, end_dt)).select_related('invoice', 'product', 'device')
    for item in sale_items:
        if item.product.requires_imei and item.device:
            cost = item.device.cost
            unit_cost = item.device.cost
            cogs_serialized += cost
        else:
            cost = item.quantity * item.product.average_cost
            unit_cost = item.product.average_cost
            cogs_bulk += cost
        cogs_list.append({
            'invoice': item.invoice,
            'product': item.product,
            'quantity': item.quantity,
            'unit_cost': unit_cost,
            'total_cost': cost,
            'device_imei': item.device.imei if item.device else None
        })
    total_cogs = cogs_serialized + cogs_bulk
    expenses_in_period = Expense.objects.filter(shift__start_time__range=(start_dt, end_dt))
    total_expenses = expenses_in_period.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    net_profit = total_sales_revenue - total_cogs - total_expenses
    # B. Supplier Balance Statements (Credit balances)
    suppliers = Contact.objects.filter(contact_type='supplier')
    supplier_statements = []
    for sup in suppliers:
        invoices = PurchaseInvoice.objects.filter(supplier=sup)
        total_purchased = invoices.aggregate(total=models.Sum('net_amount'))['total'] or Decimal('0.00')
        total_paid = invoices.aggregate(total=models.Sum('paid_amount'))['total'] or Decimal('0.00')
        remaining = total_purchased - total_paid
        if total_purchased > 0:
            supplier_statements.append({
                'supplier': sup,
                'total_purchased': total_purchased,
                'total_paid': total_paid,
                'remaining': remaining,
                'invoices': invoices.order_by('-invoice_date')
            })
    expenses_list = expenses_in_period.select_related('category', 'shift__cashier').order_by('-id')
    # ==========================================
    # 2. SALE REPORTS (تقارير المبيعات)
    # ==========================================
    sales_count = sales_in_period.count()
    sales_total_gross = sales_in_period.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0.00')
    sales_total_discount = sales_in_period.aggregate(total=models.Sum('discount'))['total'] or Decimal('0.00')
    payments_in_period = Payment.objects.filter(invoice__date_created__range=(start_dt, end_dt))
    payment_breakdown = {
        'cash': payments_in_period.filter(payment_method='cash').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
        'card': payments_in_period.filter(payment_method='card').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
        'wallet': payments_in_period.filter(payment_method='wallet').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
    }
    top_selling_items = SaleItem.objects.filter(invoice__date_created__range=(start_dt, end_dt))        .values('product__name')        .annotate(total_qty=models.Sum('quantity'), total_revenue=models.Sum(models.F('quantity') * models.F('unit_price')))        .order_by('-total_qty')[:5]
    # ==========================================
    # 3. PURCHASE REPORTS (تقارير المشتريات)
    # ==========================================
    purchases_in_period = PurchaseInvoice.objects.filter(invoice_date__range=(start_dt, end_dt))
    purchases_count = purchases_in_period.count()
    purchases_list = purchases_in_period.select_related('supplier', 'created_by').order_by('-invoice_date')
    purchases_total_net = purchases_in_period.aggregate(total=models.Sum('net_amount'))['total'] or Decimal('0.00')
    purchases_total_paid = purchases_in_period.aggregate(total=models.Sum('paid_amount'))['total'] or Decimal('0.00')
    purchases_total_remaining = purchases_total_net - purchases_total_paid
    purchases_by_method = {
        'cash': purchases_in_period.filter(payment_method='cash').count(),
        'credit': purchases_in_period.filter(payment_method='credit').count(),
        'partial': purchases_in_period.filter(payment_method='partial').count(),
    }
    # ==========================================
    # 4. INVENTORY REPORTS (تقارير المخزون)
    # ==========================================
    bulk_stocks = Stock.objects.filter(quantity__gt=0).select_related('product')
    total_bulk_cost_val = Decimal('0.00')
    total_bulk_selling_val = Decimal('0.00')
    for bs in bulk_stocks:
        total_bulk_cost_val += bs.quantity * bs.product.average_cost
        total_bulk_selling_val += bs.quantity * bs.product.selling_price
    devices_in_stock = Device.objects.filter(is_sold=False).select_related('product')
    total_devices_cost_val = Decimal('0.00')
    total_devices_selling_val = Decimal('0.00')
    for dev in devices_in_stock:
        total_devices_cost_val += dev.cost
        total_devices_selling_val += dev.product.selling_price
    total_cval = total_bulk_cost_val + total_devices_cost_val
    total_sval = total_bulk_selling_val + total_devices_selling_val
    expected_profit_on_stock = total_sval - total_cval
    new_devices_count = devices_in_stock.filter(condition='new').count()
    used_devices_count = devices_in_stock.filter(condition='used').count()
    accessories_count = Stock.objects.filter(product__product_type='accessory', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    spare_parts_count = Stock.objects.filter(product__product_type='spare_part', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    accessories_in_stock = Stock.objects.filter(product__product_type='accessory', quantity__gt=0).select_related('product', 'warehouse')
    spare_parts_in_stock = Stock.objects.filter(product__product_type='spare_part', quantity__gt=0).select_related('product', 'warehouse')
    low_stock_items = Stock.objects.filter(quantity__lt=5).select_related('product', 'warehouse')

    # 4.B. All products list with stock counts and pagination
    from django.core.paginator import Paginator
    from django.db.models import Sum, Count, Q, OuterRef, Subquery, Value, IntegerField, Case, When
    from django.db.models.functions import Coalesce

    # Subquery to sum Stock quantity (for bulk items)
    stock_subquery = Stock.objects.filter(product=OuterRef('pk')).values('product').annotate(total=Sum('quantity')).values('total')

    # Subquery to count unsold Devices (for serialized items)
    device_subquery = Device.objects.filter(product=OuterRef('pk'), is_sold=False).values('product').annotate(total=Count('id')).values('total')

    products_qs = Product.objects.annotate(
        bulk_qty=Coalesce(Subquery(stock_subquery), Value(0)),
        device_qty=Coalesce(Subquery(device_subquery), Value(0))
    ).annotate(
        total_qty=Case(
            When(requires_imei=True, then='device_qty'),
            default='bulk_qty',
            output_field=IntegerField()
        )
    ).order_by('name')

    inv_search = request.GET.get('inv_search', '').strip()
    if inv_search:
        products_qs = products_qs.filter(
            Q(name__icontains=inv_search) |
            Q(barcode_qr__exact=inv_search) |
            Q(barcode_qr__icontains=inv_search)
        )

    paginator = Paginator(products_qs, 10)
    page_number = request.GET.get('page', 1)
    products_page = paginator.get_page(page_number)
    # ==========================================
    # 5. MAINTENANCE REPORTS (������ �������)
    # ==========================================
    tickets_in_period = RepairTicket.objects.filter(created_at__range=(start_dt, end_dt))
    tickets_count = tickets_in_period.count()
    tickets_status_breakdown = {
        'pending': tickets_in_period.filter(status='pending').count(),
        'in_progress': tickets_in_period.filter(status='in_progress').count(),
        'waiting_parts': tickets_in_period.filter(status='waiting_parts').count(),
        'done': tickets_in_period.filter(status='done').count(),
        'delivered': tickets_in_period.filter(status='delivered').count(),
    }
    tech_performance = RepairTicket.objects.filter(created_at__range=(start_dt, end_dt)) \
        .values('technician__username') \
        .annotate(tickets_done=models.Count('id', filter=models.Q(status='delivered') | models.Q(status='done')),
                  total_labor=models.Sum('labor_cost')) \
        .order_by('-total_labor')
    parts_consumed = RepairPartUsed.objects.filter(ticket__created_at__range=(start_dt, end_dt)).select_related('product')
    total_parts_cost = Decimal('0.00')
    total_parts_price = Decimal('0.00')
    for p in parts_consumed:
        total_parts_cost += p.quantity * p.product.average_cost
        total_parts_price += p.quantity * p.price
    total_labor = tickets_in_period.aggregate(total=models.Sum('labor_cost'))['total'] or Decimal('0.00')
    parts_profit = total_parts_price - total_parts_cost
    total_profit = total_labor + parts_profit

    # Fetch and filter tickets list for detailed report
    tickets_qs = RepairTicket.objects.filter(created_at__range=(start_dt, end_dt)).select_related('customer', 'technician').prefetch_related('parts_used__product').order_by('-created_at')
    maint_search = request.GET.get('maint_search', '').strip()
    if maint_search:
        tickets_qs = tickets_qs.filter(
            models.Q(customer__name__icontains=maint_search) |
            models.Q(technician__username__icontains=maint_search) |
            models.Q(device_model__icontains=maint_search) |
            models.Q(device_imei__icontains=maint_search) |
            models.Q(status__icontains=maint_search)
        )
    
    # Calculate parts total for each ticket in the query
    for ticket in tickets_qs:
        ticket.parts_total = sum(part.price * part.quantity for part in ticket.parts_used.all())

    maint_paginator = Paginator(tickets_qs, 10)
    maint_page_number = request.GET.get('maint_page', 1)
    tickets_page = maint_paginator.get_page(maint_page_number)
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'financials': {
            'total_sales_revenue': total_sales_revenue,
            'total_cogs': total_cogs,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'supplier_statements': supplier_statements,
            'expenses_list': expenses_list[:20],
            'expenses_all': expenses_list,
            'sales_list': sales_list,
            'cogs_list': cogs_list,
        },
        'sales': {
            'count': sales_count,
            'gross': sales_total_gross,
            'discount': sales_total_discount,
            'net': total_sales_revenue,
            'payment_breakdown': payment_breakdown,
            'top_items': top_selling_items,
        },
        'purchases': {
            'count': purchases_count,
            'total_net': purchases_total_net,
            'total_paid': purchases_total_paid,
            'total_remaining': purchases_total_remaining,
            'by_method': purchases_by_method,
            'purchases_list': purchases_list,
        },
        'inventory': {
            'cost_valuation': total_cval,
            'selling_valuation': total_sval,
            'expected_profit': expected_profit_on_stock,
            'new_devices': new_devices_count,
            'used_devices': used_devices_count,
            'accessories_count': accessories_count,
            'spare_parts_count': spare_parts_count,
            'accessories_stock': accessories_in_stock,
            'spare_parts_stock': spare_parts_in_stock,
            'low_stock_items': low_stock_items,
            'products_page': products_page,
            'inv_search': inv_search,
        },
        'maintenance': {
            'count': tickets_count,
            'status_breakdown': tickets_status_breakdown,
            'tech_performance': tech_performance,
            'parts_cost': total_parts_cost,
            'tickets_page': tickets_page,
            'maint_search': maint_search,
            'total_labor': total_labor,
            'parts_profit': parts_profit,
            'total_profit': total_profit,
            'tickets_list': tickets_in_period.select_related('customer', 'technician').prefetch_related('parts_used__product').order_by('-created_at'),
        }
    }
    if request.headers.get('HX-Request'):
        target = request.headers.get('HX-Target')
        if target == 'inventory-products-table-container':
            return render(request, 'erp/includes/reports_inventory_table.html', context)
        elif target == 'maintenance-tickets-table-container':
            return render(request, 'erp/includes/reports_maintenance_table.html', context)
    return render(request, 'erp/reports.html', context)
