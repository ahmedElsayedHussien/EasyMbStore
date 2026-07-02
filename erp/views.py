# -*- coding: utf-8 -*-
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied, ValidationError
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
from decimal import Decimal
from django.contrib import messages
from erp.models import (
    Branch, StoreSetting, Contact, Warehouse, Product, Stock, Device, DeviceAttachment,
    PurchaseInvoice, PurchaseItem, StockTransfer, StockTransferItem,
    CashShift, Expense, ExpenseCategory, SaleInvoice, SaleItem, Payment,
    RepairTicket, RepairPartUsed, Warranty, NotificationLog, Treasury, ContactTransaction
)
from erp.forms import (
    ContactForm, UsedDeviceForm, DeviceAttachmentFormSet,
    PurchaseInvoiceForm, PurchaseItemFormSet,
    StockTransferForm, StockTransferItemFormSet,
    RepairTicketForm, RepairPartUsedFormSet,
    CashShiftOpenForm, CashShiftCloseForm, ExpenseForm,
    WarehouseForm, SupplierForm, CustomerForm, TreasuryForm, ProductForm, SystemUserCreationForm, ContactTransactionForm
)
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def require_specific_branch(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.branch is None:
            messages.warning(request, 'يجب تحديد فرع معين للقيام بهذه العملية (لا يمكن استخدام كل الفروع).')
            return redirect('erp:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@login_required
@require_POST
def switch_branch(request):
    branch_id = request.POST.get('branch_id')
    if branch_id:
        request.session['active_branch_id'] = branch_id
    # إعادة توجيه للصفحة السابقة أو للرئيسية
    next_url = request.POST.get('next', 'erp:dashboard')
    if not next_url.startswith('/'):
        from django.urls import reverse
        try:
            next_url = reverse(next_url)
        except:
            next_url = reverse('erp:dashboard')
    return redirect(next_url)

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
    total_sales = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).aggregate(total=models.Sum('net_amount'))['total'] or 0.00
    # الوردية المفتوحة الحالية للمستخدم
    active_shift = CashShift.objects.filter(cashier=request.user, status='open').first()
    active_shift_balance = active_shift.expected_closing_balance if active_shift else 0.00
    # تذاكر الصيانة النشطة
    active_repairs_count = RepairTicket.objects.exclude(status='delivered').count()
    from django.utils.timezone import now
    from django.db.models import Sum
    current_date = now()
    start_of_month = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # مبيعات الشهر الحالي
    current_month_sales = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__gte=start_of_month).aggregate(total=Sum('net_amount'))['total'] or 0.00
    # مشتريات الشهر الحالي
    current_month_purchases = PurchaseInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice_date__gte=start_of_month).aggregate(total=Sum('net_amount'))['total'] or 0.00
    # مصروفات الشهر الحالي
    current_month_expenses = Expense.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, shift__start_time__gte=start_of_month).aggregate(total=Sum('amount'))['total'] or 0.00
    
    # أكثر الأصناف مبيعاً هذا الشهر
    top_selling_products = Product.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, saleitem__invoice__date_created__gte=start_of_month)\
                                          .annotate(total_sold=Sum('saleitem__quantity'))\
                                          .order_by('-total_sold')[:5]
                                          
    # أقل الأصناف مبيعاً هذا الشهر
    least_selling_products = Product.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, saleitem__invoice__date_created__gte=start_of_month)\
                                            .annotate(total_sold=Sum('saleitem__quantity'))\
                                            .filter(total_sold__gt=0)\
                                            .order_by('total_sold')[:5]

    # النواقص (أصناف كميتها في أي مخزن أقل من 5)
    low_stock_items = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, quantity__lt=5).select_related('product', 'warehouse')
    # آخر فواتير بيع
    recent_sales = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('-date_created')[:5].select_related('customer', 'cashier')
    # آخر تذاكر صيانة
    recent_tickets = RepairTicket.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('-id')[:5].select_related('customer', 'technician')
    # سجل الإشعارات
    recent_notifications = NotificationLog.objects.order_by('-sent_at')[:5].select_related('customer')
    # البحث السريع بـ QR/الباركود
    search_query = request.GET.get('q', '').strip()
    search_result = None
    if search_query:
        # البحث عن منتج بالباركود
        product = Product.objects.filter(barcode_qr=search_query, branch__in=[request.branch] if request.branch else request.user_allowed_branches).first()
        if product:
            # إحضار تفاصيل المخزون والأجهزة
            stocks = Stock.objects.filter(product=product, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('warehouse')
            unsold_devices = Device.objects.filter(product=product, is_sold=False, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('warehouse')
            search_result = {
                'type': 'product',
                'object': product,
                'stocks': stocks,
                'devices': unsold_devices,
            }
        else:
            # البحث عن جهاز سيريال IMEI
            device = Device.objects.filter(models.Q(imei=search_query) | models.Q(imei2=search_query), warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse', 'purchased_from').first()
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
        'search_query': search_query,
        'search_result': search_result,
        'current_month_sales': current_month_sales,
        'current_month_purchases': current_month_purchases,
        'current_month_expenses': current_month_expenses,
        'top_selling_products': top_selling_products,
        'least_selling_products': least_selling_products,
    }
    return render(request, 'erp/dashboard.html', context)
# ==========================================
# 2. نقطة البيع (Point of Sale - POS)
# ==========================================
@login_required
@permission_required('erp.add_saleinvoice', raise_exception=True)
@require_specific_branch
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
    products = Product.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).annotate(
        available_qty=Coalesce(
            Case(
                When(requires_imei=True, then=Count('device', filter=Q(device__is_sold=False, device__warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches))),
                default=Sum('stock__quantity', filter=Q(stock__warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches)),
                output_field=IntegerField()
            ),
            Value(0)
        )
    ).filter(available_qty__gt=0)[:12]
    card_list = []
    for prod in products:
        if prod.requires_imei:
            new_qty = prod.device_set.filter(is_sold=False, condition='new', warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).count()
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
            used_qty = prod.device_set.filter(is_sold=False, condition='used', warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).count()
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
    warehouses = Warehouse.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    customers = Contact.objects.filter(contact_type__in=['customer', 'used_seller'], branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    warehouse_stocks = Stock.objects.filter(quantity__gt=0, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse')
    # الأجهزة المتاحة للبيع
    available_devices = Device.objects.filter(is_sold=False, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse')
    context = {
        'active_shift': active_shift,
        'store_setting': store_setting,
        'products': card_list,
        'warehouses': warehouses,
        'customers': customers,
        'available_devices': available_devices,
        'warehouse_stocks': warehouse_stocks,
        'product_types': Product.PRODUCT_TYPES,
    }
    return render(request, 'erp/pos.html', context)
@login_required
@require_specific_branch
def pos_product_search(request):
    """
    مستدعى للبحث السريع عن الباركود أثناء إضافته من قارئ الباركود.
    """
    code = request.GET.get('code', '').strip()
    product = Product.objects.filter(barcode_qr=code, branch__in=[request.branch] if request.branch else request.user_allowed_branches).first()
    if not product:
        # البحث في الأجهزة بالسيريال
        device = Device.objects.filter(models.Q(imei=code) | models.Q(imei2=code), is_sold=False, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse').first()
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
@require_specific_branch
def pos_product_grid(request):
    """
    مستدعى ديناميكياً لتحديث شبكة المنتجات بالبحث و/أو القسم (HTMX AJAX search).
    """
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    from django.db.models import Sum, Count, Q, Case, When, Value, IntegerField
    from django.db.models.functions import Coalesce
    products = Product.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).annotate(
        available_qty=Coalesce(
            Case(
                When(requires_imei=True, then=Count('device', filter=Q(device__is_sold=False, device__warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches))),
                default=Sum('stock__quantity', filter=Q(stock__warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches)),
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
            new_qty = prod.device_set.filter(is_sold=False, condition='new', warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).count()
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
            used_qty = prod.device_set.filter(is_sold=False, condition='used', warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).count()
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
@require_specific_branch
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
    
    # بطاقات الهدايا والنقاط
    points_redeemed = int(data.get('points_redeemed', 0))
    gift_card_code = data.get('gift_card_code', '').strip()
    
    items_data = data.get('items', [])
    payments_data = data.get('payments', [])
    if not items_data:
        return JsonResponse({'error': 'لا يمكن حفظ فاتورة خالية من الأصناف'}, status=400)
    try:
        with transaction.atomic():
            customer = get_object_or_404(Contact, id=customer_id)
            # 1. إنشاء رأس الفاتورة
            invoice = SaleInvoice(
                branch__in=[request.branch] if request.branch else request.user_allowed_branches,
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
                try:
                    traded_device = Device.objects.select_for_update().get(id=traded_in_device_id)
                except Device.DoesNotExist:
                    raise ValidationError("جهاز الاستبدال المحدد غير موجود.")
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
                    try:
                        # نستخدم select_for_update() لحجز القفل على مستوى الصف ومنع تسابق العمليات
                        device = Device.objects.select_for_update().get(id=device_id)
                    except Device.DoesNotExist:
                        raise ValidationError("الجهاز المحدد غير موجود.")
                    # التحقق من أن الجهاز ليس مباعاً بالفعل
                    if device.is_sold:
                        raise ValidationError(f"الجهاز بالسيريال {device.imei} مباع بالفعل.")
                    sale_item.device = device
                    sale_item.quantity = 1  # الهاتف المسرين كميته دائماً 1
                sale_item.save()  # سيقوم الـ Signal بخصم المخزن
                total_sum += sale_item.quantity * unit_price
            invoice.total_amount = total_sum
            net_amount = (total_sum - discount) - trade_in_value
            
            # --- معالجة نظام نقاط الولاء وبطاقات الهدايا ---
            store_settings = StoreSetting.objects.first()
            if store_settings and store_settings.enable_loyalty_system:
                from decimal import Decimal
                from django.utils.timezone import now
                
                # 1. استبدال النقاط
                if points_redeemed > 0:
                    if customer.loyalty_points < points_redeemed:
                        raise ValidationError(f"رصيد النقاط ({customer.loyalty_points}) لا يكفي لاستبدال ({points_redeemed}) نقطة.")
                    
                    points_discount_val = (Decimal(points_redeemed) / Decimal(100)) * store_settings.egp_per_100_points
                    customer.loyalty_points -= points_redeemed
                    invoice.points_redeemed = points_redeemed
                    invoice.points_discount = points_discount_val
                    net_amount -= points_discount_val
                
                # 2. خصم بطاقة الهدايا
                if gift_card_code:
                    try:
                        gift_card = GiftCard.objects.select_for_update().get(code=gift_card_code, is_active=True)
                    except GiftCard.DoesNotExist:
                        raise ValidationError("كود بطاقة الهدية غير صالح أو غير مفعل.")
                        
                    if gift_card.expires_at and gift_card.expires_at < now().date():
                        raise ValidationError("بطاقة الهدية منتهية الصلاحية.")
                        
                    if gift_card.current_balance > 0 and net_amount > 0:
                        deduction = min(gift_card.current_balance, net_amount)
                        gift_card.current_balance -= deduction
                        # Single-use GC
                        gift_card.is_active = False 
                        gift_card.save()
                        
                        invoice.gift_card = gift_card
                        invoice.gift_card_deduction = deduction
                        net_amount -= deduction
                    elif gift_card.current_balance <= 0:
                        raise ValidationError("رصيد بطاقة الهدية نافد (صفر).")
                
                # 3. احتساب النقاط المكتسبة على المتبقي الذي سيُدفع (قبل احتساب المديونية)
                if net_amount > 0 and customer.contact_type == 'customer':
                    earned = int(net_amount * store_settings.loyalty_points_per_egp)
                    invoice.points_earned = earned
                    customer.loyalty_points += earned
                
                customer.save()
            # ---------------------------------------------
            
            invoice.net_amount = net_amount
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
            # التحقق من المديونية والبيع الآجل
            if total_paid < invoice.net_amount:
                if customer.name == 'عميل نقدي' or customer.contact_type != 'customer':
                    raise ValidationError("لا يمكن البيع بالآجل لـ 'عميل نقدي' الافتراضي. الرجاء اختيار اسم العميل الصحيح لتقييد المديونية عليه.")
                invoice.payment_method = 'partial' if total_paid > 0 else 'credit'
            elif total_paid > invoice.net_amount:
                raise ValidationError(f"المجموع المدفوع ({total_paid}) أكبر من صافي الفاتورة ({invoice.net_amount})")
            else:
                invoice.payment_method = 'cash'
                
            invoice.paid_amount = total_paid
            invoice.save()
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

@login_required
@require_specific_branch
def pos_inventory_snapshot(request):
    """
    إرجاع قائمة الأجهزة المتاحة وكميات المخازن بصيغة JSON لتحديث نقطة البيع تلقائياً بدون تحديث الصفحة.
    """
    from erp.models import Device, Stock
    
    # 1. الأجهزة المتاحة (سيريالات الهواتف)
    available_devices = Device.objects.filter(is_sold=False).select_related('product', 'warehouse')
    devices_data = []
    for dev in available_devices:
        devices_data.append({
            "id": dev.id,
            "product_id": dev.product.id,
            "imei": f"{dev.imei} / {dev.imei2}" if dev.imei2 else dev.imei,
            "warehouse_id": dev.warehouse.id,
            "condition": dev.condition,
            "storage": dev.get_storage_display() or "",
            "ram": dev.get_ram_display() or ""
        })
        
    # 2. الأصناف السائبة (مخزون المستودعات)
    warehouse_stocks = Stock.objects.filter(quantity__gt=0).select_related('product', 'warehouse')
    stocks_data = []
    for st in warehouse_stocks:
        stocks_data.append({
            "product_id": st.product.id,
            "warehouse_id": st.warehouse.id,
            "quantity": st.quantity
        })
        
    return JsonResponse({
        "devices": devices_data,
        "stocks": stocks_data
    })
# ==========================================
# 3. شراء الأجهزة المستعملة (Used Device Purchase)
# ==========================================
@login_required
@permission_required('erp.add_device', raise_exception=True)
@require_specific_branch
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
                    
                    # سداد مبلغ الهاتف من الخزينة المحددة
                    treasury = device_form.cleaned_data.get('treasury')
                    cost = device_instance.cost or 0
                    if treasury and cost > 0:
                        treasury_obj = Treasury.objects.select_for_update().get(id=treasury.id)
                        if cost > treasury_obj.balance:
                            raise ValidationError(f"رصيد الخزينة المحددة ({treasury_obj.balance} ج.م) لا يكفي لسداد قيمة الهاتف ({cost} ج.م).")
                        treasury_obj.balance -= cost
                        treasury_obj.save()
                        
                        # تسجيل الحركة على البائع كمورد
                        ContactTransaction.objects.create(
                            contact=seller_instance,
                            treasury=treasury_obj,
                            transaction_type='payment',
                            amount=cost,
                            description=f"سداد قيمة هاتف مستعمل IMEI: {device_instance.imei}",
                            user=request.user
                        )
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
@permission_required('erp.change_device', raise_exception=True)
@require_specific_branch
def used_device_return(request, pk):
    device = get_object_or_404(Device, pk=pk)
    
    if request.method == 'POST':
        treasury_id = request.POST.get('treasury_id')
        if not treasury_id:
            messages.error(request, "يجب تحديد الخزينة التي سيتم استرداد المبلغ إليها.")
            return redirect('erp:device_history', pk=pk)
            
        try:
            with transaction.atomic():
                treasury = Treasury.objects.select_for_update().get(pk=treasury_id)
                
                # تحديث حالة الجهاز بأنه تم إرجاعه للبائع
                device.is_returned_to_seller = True
                device.save()
                
                cost = device.cost or 0
                if cost > 0 and device.purchased_from:
                    treasury.balance += cost
                    treasury.save()
                    
                    # تسجيل استرداد المبلغ كحركة إيصال (قبض) من البائع
                    ContactTransaction.objects.create(
                        contact=device.purchased_from,
                        treasury=treasury,
                        transaction_type='receipt',
                        amount=cost,
                        description=f"استرداد مبلغ الهاتف المستعمل IMEI: {device.imei} بسبب الإرجاع للبائع",
                        user=request.user
                    )
                
                messages.success(request, f"تم إرجاع الجهاز المستعمل ({device.imei}) للبائع بنجاح واسترداد مبلغه إلى الخزينة.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الإرجاع: {str(e)}")
            
    return redirect('erp:device_history', pk=pk)
@login_required
@permission_required('erp.add_device', raise_exception=True)
@require_specific_branch
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
    purchases = PurchaseInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('-invoice_date').select_related('supplier', 'created_by')
    has_open_shift = CashShift.objects.filter(cashier=request.user, status='open', branch__in=[request.branch] if request.branch else request.user_allowed_branches).exists()
    active_treasuries = Treasury.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    return render(request, 'erp/purchase_list.html', {
        'purchases': purchases,
        'has_open_shift': has_open_shift,
        'active_treasuries': active_treasuries
    })
@login_required
@permission_required('erp.add_purchaseinvoice', raise_exception=True)
@require_specific_branch
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
                    
                    # خصم المبلغ المدفوع من الخزينة المحددة
                    if invoice.paid_amount > 0:
                        if not invoice.treasury:
                            raise Exception("خطأ: يرجى تحديد الخزينة التي تم سداد المبلغ منها.")
                        treasury = Treasury.objects.select_for_update().get(id=invoice.treasury.id)
                        if invoice.paid_amount > treasury.balance:
                            raise Exception(f"خطأ: رصيد الخزينة المحددة ({treasury.balance} ج.م) غير كافٍ لسداد المبلغ المدفوع ({invoice.paid_amount} ج.م).")
                        treasury.record_transaction(invoice.paid_amount, 'out', f'سداد فاتورة مشتريات رقم {invoice.id}', request.user)
                    
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
    has_open_shift = CashShift.objects.filter(cashier=request.user, status='open').exists()
    active_treasuries = Treasury.objects.filter(is_active=True)
    # تفكيك السيريالات وعرضها بشكل مرتب إذا وجد
    for item in items:
        if item.product.requires_imei and item.imei_list:
            item.imeis = [imei.strip() for imei in item.imei_list.split(',') if imei.strip()]
    context = {
        'invoice': invoice,
        'items': items,
        'store_setting': store_setting,
        'has_open_shift': has_open_shift,
        'active_treasuries': active_treasuries,
    }
    return render(request, 'erp/purchase_invoice_detail.html', context)

@login_required
@permission_required('erp.change_purchaseinvoice', raise_exception=True)
@require_specific_branch
def purchase_invoice_pay(request, pk):
    """
    تسجيل سداد دفعة لفاتورة مشتريات مورد (نقداً أو آجل).
    """
    from decimal import Decimal
    from django.contrib import messages
    from erp.models import Expense, ExpenseCategory, CashShift, PurchaseInvoice
    
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        deduct_from_shift = request.POST.get('deduct_from_shift') == 'on'
        
        try:
            amount = Decimal(amount_str)
        except (ValueError, TypeError):
            messages.error(request, "خطأ: قيمة غير صالحة للمبلغ.")
            return redirect('erp:purchase_list')
            
        if amount <= 0:
            messages.error(request, "خطأ: يجب أن يكون مبلغ السداد أكبر من صفر.")
            return redirect('erp:purchase_list')

        with transaction.atomic():
            invoice = get_object_or_404(PurchaseInvoice.objects.select_for_update(), pk=pk)
            
            remaining = invoice.remaining_amount
            if amount > remaining:
                messages.error(request, f"خطأ: لا يمكن سداد مبلغ أكبر من المبلغ المتبقي ({remaining} ج.م).")
                return redirect('erp:purchase_list')
                
            # إذا تم طلب الخصم من الوردية الحالية
            if deduct_from_shift:
                # التحقق من وجود وردية مفتوحة للمستخدم الحالي مع قفلها
                shift = CashShift.objects.select_for_update().filter(cashier=request.user, status='open').first()
                if not shift:
                    messages.error(request, "خطأ: لا توجد وردية مفتوحة لحسابك حالياً للخصم منها. تم إلغاء عملية السداد.")
                    next_url = request.META.get('HTTP_REFERER')
                    if next_url:
                        return redirect(next_url)
                    return redirect('erp:purchase_list')
                    
                # التحقق من كفاية الرصيد المتوفر في الوردية
                if amount > shift.expected_closing_balance:
                    messages.error(request, f"خطأ: لا يمكن سداد المبلغ من الوردية الحالية لأن النقدية المتوفرة في درج الوردية ({shift.expected_closing_balance} ج.م) أقل من المبلغ المراد سداده ({amount} ج.م).")
                    next_url = request.META.get('HTTP_REFERER')
                    if next_url:
                        return redirect(next_url)
                    return redirect('erp:purchase_list')
                    
                # إيجاد أو إنشاء تصنيف سداد الموردين
                category, created = ExpenseCategory.objects.get_or_create(name="سداد موردين")
                
                # تسجيل المصروف
                Expense.objects.create(
                    shift=shift,
                    category=category,
                    amount=amount,
                    description=f"سداد دفعة لفاتورة المشتريات رقم {invoice.supplier_invoice_number or invoice.id} للمورد {invoice.supplier.name}"
                )
            else:
                # السداد مباشرة من الخزينة المحددة
                treasury_id = request.POST.get('treasury')
                if not treasury_id:
                    messages.error(request, "خطأ: يجب تحديد الخزينة المراد السداد منها في حال عدم الخصم من الوردية.")
                    next_url = request.META.get('HTTP_REFERER')
                    if next_url:
                        return redirect(next_url)
                    return redirect('erp:purchase_list')
                
                treasury = get_object_or_404(Treasury.objects.select_for_update(), id=treasury_id)
                if amount > treasury.balance:
                    messages.error(request, f"خطأ: رصيد الخزينة المحددة ({treasury.balance} ج.م) غير كافٍ لسداد المبلغ ({amount} ج.م).")
                    next_url = request.META.get('HTTP_REFERER')
                    if next_url:
                        return redirect(next_url)
                    return redirect('erp:purchase_list')
                
                treasury.record_transaction(amount, 'out', f'دفعة لمورد: {invoice.supplier.name} للفاتورة {invoice.id}', request.user)
                
            # تحديث قيمة المبلغ المدفوع في الفاتورة
            invoice.paid_amount += amount
            invoice.save()
            
        messages.success(request, f"تم تسجيل سداد مبلغ {amount} ج.م للمورد {invoice.supplier.name} بنجاح.")
        
        # التوجيه لنفس الصفحة التي تم استدعاء الطلب منها
        next_url = request.META.get('HTTP_REFERER')
        if next_url:
            return redirect(next_url)
        return redirect('erp:purchase_list')
        
    return redirect('erp:purchase_list')

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
@require_specific_branch
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
@require_specific_branch
def transfer_complete(request, pk):
    """
    تأكيد استلام الشحنة وتحديث مواقع المخازن وتفعيل السجنل.
    """
    with transaction.atomic():
        transfer = get_object_or_404(StockTransfer.objects.select_for_update(), pk=pk)
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
    tickets = RepairTicket.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('-id').select_related('customer', 'technician')
    parts = Product.objects.filter(product_type='spare_part', branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    warehouses = Warehouse.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    from django.contrib.auth.models import User
    technicians = User.objects.filter(groups__name='فني الصيانة')
    treasuries = Treasury.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    context = {
        'tickets': tickets,
        'parts': parts,
        'warehouses': warehouses,
        'technicians': technicians,
        'treasuries': treasuries,
    }
    return render(request, 'erp/repairs.html', context)
@login_required
@permission_required('erp.add_repairticket', raise_exception=True)
@require_specific_branch
def repair_ticket_create(request):
    if request.method == 'POST':
        form = RepairTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save()
            messages.success(request, f"تم فتح تذكرة الصيانة #{ticket.id} بنجاح.")
            return redirect('erp:repair_list')
    else:
        parent_id = request.GET.get('parent_id')
        initial_data = {}
        if parent_id:
            try:
                parent_ticket = RepairTicket.objects.get(id=parent_id)
                initial_data = {
                    'customer': parent_ticket.customer_id,
                    'device_model': parent_ticket.device_model,
                    'device_imei': parent_ticket.device_imei,
                    'parent_ticket': parent_ticket.id,
                    'labor_cost': 0, # افتراض أن تذكرة الضمان بدون مصنعية إضافية مبدئياً
                    'issue_description': f"متابعة للتذكرة السابقة #{parent_ticket.id}:\n"
                }
                messages.info(request, "تم تعبئة البيانات تلقائياً بناءً على تذكرة الضمان السابقة.")
            except RepairTicket.DoesNotExist:
                pass
        form = RepairTicketForm(initial=initial_data)
    return render(request, 'erp/repair_create.html', {'form': form})
@login_required
@permission_required('erp.change_repairticket', raise_exception=True)
@require_POST
@require_specific_branch
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
@require_specific_branch
def repair_change_status(request, pk):
    """
    تعديل حالة الصيانة وإرسال إشعار للعميل عبر Django Q2 في الخلفية.
    """
    from django_q.tasks import async_task
    from erp.models import NotificationLog, NotificationSettings

    ticket = get_object_or_404(RepairTicket, pk=pk)
    new_status = request.POST.get('status')
    treasury_id = request.POST.get('treasury_id')

    if new_status in dict(RepairTicket.STATUS_CHOICES):
        if new_status == 'delivered':
            if not treasury_id:
                return JsonResponse({'error': 'يجب تحديد الخزينة عند تسليم الجهاز لتحصيل المبلغ.'}, status=400)
            try:
                treasury = Treasury.objects.select_for_update().get(id=treasury_id, is_active=True)
                total_cost = ticket.total_cost
                if total_cost > 0:
                    treasury.record_transaction(total_cost, 'in', f'تحصيل تكلفة صيانة لتذكرة رقم #{ticket.id}', request.user)
                    # إنشاء إيصال للعميل كإيراد صيانة
                    from erp.models import ContactTransaction
                    ContactTransaction.objects.create(
                        contact=ticket.customer,
                        treasury=treasury,
                        transaction_type='receipt',
                        amount=total_cost,
                        description=f"تحصيل تكلفة صيانة لتذكرة رقم #{ticket.id}",
                        user=request.user
                    )
            except Treasury.DoesNotExist:
                return JsonResponse({'error': 'الخزينة المحددة غير موجودة أو غير نشطة.'}, status=400)

        ticket.status = new_status
        ticket.save()
        status_display = ticket.get_status_display()

        notif_settings = NotificationSettings.get_settings()
        template_map = {
            'pending':       ('msg_pending_enabled',       'msg_pending'),
            'in_progress':   ('msg_in_progress_enabled',   'msg_in_progress'),
            'waiting_parts': ('msg_waiting_parts_enabled', 'msg_waiting_parts'),
            'done':          ('msg_done_enabled',           'msg_done'),
            'delivered':     ('msg_delivered_enabled',     'msg_delivered'),
        }
        enabled_key, template_key = template_map.get(new_status, (None, None))
        should_send = enabled_key and getattr(notif_settings, enabled_key, False)

        if should_send and ticket.customer.phone:
            msg = notif_settings.render_template(template_key, ticket)
            log = NotificationLog.objects.create(
                customer=ticket.customer,
                ticket=ticket,
                notification_type='whatsapp',
                message_body=msg,
                status='queued',
            )
            async_task(
                'erp.tasks.send_whatsapp_notification',
                log_id=log.id,
                task_name=f"whatsapp_ticket_{ticket.id}_{new_status}",
            )

        return JsonResponse({'status': 'success', 'new_status_display': status_display})
    return JsonResponse({'error': 'حالة غير صالحة'}, status=400)
@login_required
@permission_required('erp.change_repairticket', raise_exception=True)
@require_POST
@require_specific_branch
def repair_ticket_edit(request, pk):
    """
    تحديث بيانات التذكرة (المصنعية، حالة التذكرة، وصف العطل، الفني المسؤول).
    """
    ticket = get_object_or_404(RepairTicket, pk=pk)
    labor_cost = request.POST.get('labor_cost')
    issue_description = request.POST.get('issue_description')
    technician_id = request.POST.get('technician_id')
    status = request.POST.get('status')
    treasury_id = request.POST.get('treasury_id')
    try:
        if labor_cost is not None:
            ticket.labor_cost = models.DecimalField(max_digits=10, decimal_places=2).to_python(labor_cost)
        if issue_description is not None:
            ticket.issue_description = issue_description.strip()
        if status in dict(RepairTicket.STATUS_CHOICES):
            if ticket.status != status:
                if status == 'delivered':
                    if not treasury_id:
                        return JsonResponse({'error': 'يجب تحديد الخزينة عند تسليم الجهاز لتحصيل المبلغ.'}, status=400)
                    try:
                        treasury = Treasury.objects.select_for_update().get(id=treasury_id, is_active=True)
                        total_cost = ticket.total_cost
                        if total_cost > 0:
                            treasury.record_transaction(total_cost, 'in', f"تحصيل تكلفة صيانة لتذكرة رقم #{ticket.id}", request.user)
                            from erp.models import ContactTransaction
                            ContactTransaction.objects.create(
                                contact=ticket.customer,
                                treasury=treasury,
                                transaction_type='receipt',
                                amount=total_cost,
                                description=f"تحصيل تكلفة صيانة لتذكرة رقم #{ticket.id}",
                                user=request.user
                            )
                    except Treasury.DoesNotExist:
                        return JsonResponse({'error': 'الخزينة المحددة غير موجودة أو غير نشطة.'}, status=400)
                        
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
@require_specific_branch
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
            form = CashShiftOpenForm(request.POST, user=request.user)
            if form.is_valid():
                shift = form.save(commit=False)
                shift.cashier = request.user
                shift.status = 'open'
                shift.save()
                messages.success(request, "تم فتح الوردية بنجاح. يومك مبارك ورزقك واسع!")
                return redirect('erp:shift_manage')
        else:
            form = CashShiftOpenForm(user=request.user)
        
        # تمرير أرصدة الخزن لتعبئة رصيد البداية ديناميكياً
        if request.user.is_superuser or request.user.groups.filter(name='المدير العام').exists():
            user_treasuries = Treasury.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
        else:
            user_treasuries = Treasury.objects.filter(user=request.user, is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches)
        balances_map = {t.id: float(t.balance) for t in user_treasuries}
        
        return render(request, 'erp/shift_open.html', {
            'form': form,
            'treasury_balances_json': json.dumps(balances_map)
        })
@login_required
@permission_required('erp.add_expense', raise_exception=True)
@require_POST
@require_specific_branch
def shift_add_expense(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'error': 'غير مسموح للكاشير بتسجيل مصروفات'}, status=403)
    
    with transaction.atomic():
        active_shift = CashShift.objects.select_for_update().filter(cashier=request.user, status='open').first()
        if not active_shift:
            return JsonResponse({'error': 'لا توجد وردية مفتوحة لتسجيل المصاريف'}, status=400)
        
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.branch = request.branch
            expense.shift = active_shift
            # التأكد من توفر رصيد في الخزينة المحددة
            if expense.treasury and expense.amount > expense.treasury.balance:
                return JsonResponse({
                    'error': f'عذراً، الرصيد المتوفر في الخزينة ({expense.treasury.name}) هو {expense.treasury.balance} ج.م فقط.'
                }, status=400)
                
            expense.save() # ستقوم دالة الحفظ بخصم القيمة من الخزينة
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
@require_specific_branch
def shift_close(request):
    with transaction.atomic():
        active_shift = CashShift.objects.select_for_update().filter(cashier=request.user, status='open').first()
        if not active_shift:
            messages.error(request, "لا توجد وردية مفتوحة لإغلاقها.")
            return redirect('erp:shift_manage')
        form = CashShiftCloseForm(request.POST, instance=active_shift)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.status = 'closed'
            shift.end_time = timezone.now()
            shift.save() # سيقوم الـ pre_save بتحديث expected_closing_balance للمرة الأخيرة
            if shift.treasury:
                treasury = Treasury.objects.select_for_update().get(id=shift.treasury.id)
                treasury.record_transaction((shift.actual_cash - shift.opening_balance), 'in', f'فائض وردية: {shift.cashier.username}', request.user)
            discrepancy = shift.actual_cash - shift.expected_closing_balance
            if discrepancy == 0:
                messages.success(request, "تم إغلاق الوردية وتصفيتها بنجاح بدون أي فروقات.")
            elif discrepancy > 0:
                messages.warning(request, f"تم إغلاق الوردية بوجود فائض قدره {discrepancy} ج.م.")
            else:
                messages.error(request, f"تم إغلاق الوردية بوجود عجز قدره {abs(discrepancy)} ج.م.")
            return redirect('erp:dashboard')
    return redirect('erp:shift_manage')

@login_required
@permission_required('erp.view_cashshift', raise_exception=True)
def cash_status(request):
    """
    شاشة حالة النقدية: تعرض الخزائن والأرصدة الحالية
    """
    treasuries = Treasury.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('-balance')
    
    # حساب إجمالي النقدية
    total_cash = sum(t.balance for t in treasuries)
    
    context = {
        'treasuries': treasuries,
        'total_cash': total_cash,
    }
    return render(request, 'erp/cash_status.html', context)
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
    treasuries = Treasury.objects.filter(is_active=True)
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
        'treasuries': treasuries,
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
    from erp.forms import StoreSettingForm
    
    store_setting_obj = StoreSetting.objects.first()
    store_setting_form = StoreSettingForm(instance=store_setting_obj)
    
    # تهيئة النماذج الفارغة بشكل افتراضي للعرض
    warehouse_form = WarehouseForm()
    supplier_form = SupplierForm()
    customer_form = CustomerForm()
    treasury_form = TreasuryForm()
    product_form = ProductForm()
    user_form = SystemUserCreationForm()
    
    # معالجة طلبات الإدخال (POST)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_store_settings':
            store_setting_form = StoreSettingForm(request.POST, request.FILES, instance=store_setting_obj)
            if store_setting_form.is_valid():
                store_setting_form.save()
                messages.success(request, "تم حفظ الإعدادات العامة بنجاح.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "حدث خطأ في حفظ الإعدادات العامة.")
        elif action == 'update_branch':
            from erp.models import Branch
            from erp.forms import BranchForm
            branch_id = request.POST.get('branch_id')
            branch = get_object_or_404(Branch, id=branch_id)
            form = BranchForm(request.POST, instance=branch)
            if form.is_valid():
                form.save()
                messages.success(request, f"تم تحديث بيانات الفرع {branch.name} بنجاح.")
            else:
                messages.error(request, f"حدث خطأ في تحديث بيانات الفرع {branch.name}.")
            return redirect('erp:setup_dashboard')
        elif action == 'add_warehouse':
            form = WarehouseForm(request.POST)
            if form.is_valid():
                warehouse = form.save(commit=False)
                if request.branch:
                    warehouse.branch = request.branch
                warehouse.save()
                branch_name = request.branch.name if request.branch else ''
                messages.success(request, f"تم تسجيل المخزن الجديد بنجاح في الفرع '{branch_name}'.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات المخزن.")
                warehouse_form = form # احتفاظ بالنموذج غير الصالح لعرض الأخطاء
        elif action == 'add_treasury':
            form = TreasuryForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "تم إضافة الخزينة الجديدة بنجاح.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في بيانات الخزينة.")
                treasury_form = form
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
        elif action == 'add_customer':
            form = CustomerForm(request.POST)
            if form.is_valid():
                customer = form.save(commit=False)
                customer.contact_type = 'customer' # تعيين جهة الاتصال كعميل
                customer.save()
                messages.success(request, "تم تسجيل العميل الجديد بنجاح.")
                return redirect('erp:setup_dashboard')
            else:
                messages.error(request, "خطأ في إدخال بيانات العميل.")
                customer_form = form # احتفاظ بالنموذج غير الصالح لعرض الأخطاء
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

    # جلب قوائم البيانات الحالية
    from erp.models import Branch
    branches = Branch.objects.all().order_by('id')
    warehouses = Warehouse.objects.all().order_by('id')
    suppliers = Contact.objects.filter(contact_type='supplier').order_by('-id')
    customers = Contact.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, contact_type='customer').order_by('-id')
    treasuries = Treasury.objects.select_related('user').order_by('-id')
    products = Product.objects.all().order_by('-id')
    users = User.objects.filter(is_superuser=False).prefetch_related('groups').order_by('-id')
    context = {
        'store_setting_form': store_setting_form,
        'warehouse_form': warehouse_form,
        'supplier_form': supplier_form,
        'customer_form': customer_form,
        'treasury_form': treasury_form,
        'product_form': product_form,
        'user_form': user_form,
        'branches': branches,
        'warehouses': warehouses,
        'suppliers': suppliers,
        'customers': customers,
        'treasuries': treasuries,
        'products': products,
        'users': users,
    }
    return render(request, 'erp/setup.html', context)

@login_required
def debts_list(request):
    """
    شاشة مديونيات العملاء ومستحقات الموردين وسدادها
    """
    if request.method == 'POST':
        form = ContactTransactionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                trans = form.save(commit=False)
                trans.user = request.user
                
                original_amount = trans.amount
                remaining_to_distribute = original_amount
                
                # توزيع المبلغ على الفواتير المفتوحة للعميل
                if trans.transaction_type == 'receipt' and trans.contact.contact_type in ['customer', 'used_seller']:
                    unpaid_sales = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, 
                        customer=trans.contact, 
                        payment_method__in=['credit', 'partial']
                    ).order_by('date_created')
                    
                    for inv in unpaid_sales:
                        if remaining_to_distribute <= 0:
                            break
                        due = inv.remaining_amount
                        pay_amount = min(due, remaining_to_distribute)
                        
                        inv.paid_amount += pay_amount
                        if inv.remaining_amount <= 0:
                            inv.payment_method = 'cash'
                        inv.save()
                        
                        # تسجيل الدفعة على الفاتورة
                        Payment.objects.create(
                            invoice=inv,
                            payment_method='cash',
                            amount=pay_amount,
                            transaction_id=trans.description or 'سداد مديونية عامة'
                        )
                        remaining_to_distribute -= pay_amount
                
                # توزيع المبلغ على فواتير المورد
                elif trans.transaction_type == 'payment' and trans.contact.contact_type == 'supplier':
                    unpaid_purchases = PurchaseInvoice.objects.filter(
                        supplier=trans.contact,
                        payment_method__in=['credit', 'partial']
                    ).order_by('invoice_date')
                    
                    for inv in unpaid_purchases:
                        if remaining_to_distribute <= 0:
                            break
                        due = inv.remaining_amount
                        pay_amount = min(due, remaining_to_distribute)
                        
                        inv.paid_amount += pay_amount
                        if inv.remaining_amount <= 0:
                            inv.payment_method = 'cash'
                        inv.save()
                        
                        remaining_to_distribute -= pay_amount
                
                # إذا تبقى مبلغ أو لم يتم توزيعه، نحفظه كحركة عامة غير مخصصة
                if remaining_to_distribute > 0:
                    trans.amount = remaining_to_distribute
                    trans.save()
                    # الخزينة تم تحديثها تلقائياً بالباقي داخل trans.save()
                
                # تحديث الخزينة بالمبلغ الذي تم توزيعه (لأننا لم نحفظه في trans)
                distributed_amount = original_amount - remaining_to_distribute
                if distributed_amount > 0:
                    treasury = trans.treasury
                    if trans.transaction_type == 'receipt':
                        treasury.record_transaction(distributed_amount, 'in', f"سداد ديون لـ {trans.contact.name}", request.user)
                    elif trans.transaction_type == 'payment':
                        treasury.record_transaction(distributed_amount, 'out', f"سداد ديون لـ {trans.contact.name}", request.user)

                messages.success(request, f"تم تسجيل السداد بنجاح وتحديث الفواتير بقيمة {original_amount} ج.م لـ {trans.contact.name}.")
                return redirect('erp:debts_list')
        else:
            messages.error(request, "حدث خطأ في بيانات السداد، يرجى المحاولة مرة أخرى.")
    else:
        form = ContactTransactionForm()

    # جلب جميع جهات الاتصال وحساب الرصيد الحالي
    all_contacts = Contact.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches)
    customers_with_debts = []
    suppliers_with_dues = []

    for contact in all_contacts:
        balance = contact.current_balance
        if balance != 0:
            contact.calculated_balance = balance
            if contact.contact_type in ['customer', 'used_seller']:
                customers_with_debts.append(contact)
            elif contact.contact_type == 'supplier':
                suppliers_with_dues.append(contact)

    context = {
        'customers_with_debts': customers_with_debts,
        'suppliers_with_dues': suppliers_with_dues,
        'transaction_form': form,
    }
    return render(request, 'erp/debts_list.html', context)

@login_required
@permission_required('erp.view_saleinvoice', raise_exception=True)
def sale_invoice_list(request):
    """
    قائمة فواتير المبيعات مع البحث والتصفية
    """
    from django.core.paginator import Paginator
    from django.db.models import Q
    
    query = request.GET.get('q', '')
    invoices = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('customer', 'cashier').order_by('-date_created')
    
    if query:
        invoices = invoices.filter(
            Q(id__icontains=query) |
            Q(customer__name__icontains=query) |
            Q(customer__phone__icontains=query)
        )
    
    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    from erp.models import Treasury
    active_treasuries = Treasury.objects.filter(is_active=True)
    
    return render(request, 'erp/sale_invoice_list.html', {
        'page_obj': page_obj,
        'query': query,
        'active_treasuries': active_treasuries,
    })
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
@permission_required('erp.change_saleinvoice', raise_exception=True)
@require_specific_branch
def sale_invoice_pay(request, pk):
    """
    تسجيل سداد دفعة لفاتورة مبيعات عميل
    """
    from decimal import Decimal
    from django.contrib import messages
    from erp.models import SaleInvoice, Treasury, Payment
    
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        treasury_id = request.POST.get('treasury')
        
        try:
            amount = Decimal(amount_str)
        except (ValueError, TypeError):
            messages.error(request, "خطأ: قيمة غير صالحة للمبلغ.")
            return redirect('erp:sale_list')
            
        if amount <= 0:
            messages.error(request, "خطأ: يجب أن يكون مبلغ السداد أكبر من صفر.")
            return redirect('erp:sale_list')

        if not treasury_id:
            messages.error(request, "خطأ: يجب اختيار الخزينة لاستلام المبلغ.")
            return redirect('erp:sale_list')

        with transaction.atomic():
            invoice = get_object_or_404(SaleInvoice.objects.select_for_update(), pk=pk)
            
            remaining = invoice.remaining_amount
            if amount > remaining:
                messages.error(request, f"خطأ: لا يمكن سداد مبلغ أكبر من المبلغ المتبقي ({remaining} ج.م).")
                return redirect('erp:sale_list')
                
            treasury = get_object_or_404(Treasury.objects.select_for_update(), id=treasury_id)
            
            # زيادة رصيد الخزينة
            treasury.record_transaction(amount, 'in', f'فاتورة مبيعات POS رقم {invoice.id}', request.user)
            
            # إضافة الدفعة للفاتورة
            invoice.paid_amount += amount
            if invoice.paid_amount >= invoice.net_amount:
                invoice.payment_method = 'cash'
            elif invoice.paid_amount > 0:
                invoice.payment_method = 'partial'
            invoice.save()

            # إنشاء سجل الدفعة
            Payment.objects.create(
                invoice=invoice,
                payment_method='cash',
                amount=amount,
                transaction_id=f"سداد آجل - خزينة {treasury.name}"
            )

            messages.success(request, f"تم سداد مبلغ {amount} ج.م وإضافته إلى خزينة {treasury.name} بنجاح.")
            
        next_url = request.META.get('HTTP_REFERER')
        if next_url:
            return redirect(next_url)
        return redirect('erp:sale_list')
        
    return redirect('erp:sale_list')
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
    warehouses = Warehouse.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches).order_by('id')
    # استخراج الفلاتر والبحث
    warehouse_id = request.GET.get('warehouse')
    product_type = request.GET.get('type')
    search_query = request.GET.get('q', '').strip()
    # 1. المخزون السائب (Bulk Stock)
    stock_qs = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse')
    # 2. الأجهزة المسيرنة غير المباعة (Serialized Devices in Stock)
    device_qs = Device.objects.filter(is_sold=False, warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches).select_related('product', 'warehouse')
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
        'product_types': Product.PRODUCT_TYPES,
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
        SaleInvoice, SaleItem, Payment, RepairTicket, RepairPartUsed, Expense, Contact,
        CashShift, Warranty, SaleReturn, SaleReturnItem, PurchaseReturn, PurchaseReturnItem, TreasuryTransaction, ContactTransaction
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
    sales_in_period = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt))
    total_sales_revenue = sales_in_period.aggregate(total=models.Sum('net_amount'))['total'] or Decimal('0.00')
    sales_list = sales_in_period.select_related('customer', 'cashier').order_by('-date_created')

    # المرتجعات وتأثيرها على الإيرادات وتكلفة البضاعة
    sales_returns_in_period = SaleReturn.objects.filter(sale_invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt))
    total_sales_returns_amount = sales_returns_in_period.aggregate(total=models.Sum('refund_amount'))['total'] or Decimal('0.00')
    net_sales_revenue = total_sales_revenue - total_sales_returns_amount
    cogs_serialized = Decimal('0.00')
    cogs_bulk = Decimal('0.00')
    cogs_list = []
    sale_items = SaleItem.objects.filter(invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice__date_created__range=(start_dt, end_dt)).select_related('invoice', 'product', 'device')
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

    # استرداد تكلفة البضاعة المرتجعة
    returned_cogs = Decimal('0.00')
    returned_items = SaleReturnItem.objects.filter(return_invoice__sale_invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, return_invoice__date_created__range=(start_dt, end_dt)).select_related('sale_item__product', 'sale_item__device')
    for r_item in returned_items:
        if r_item.sale_item.product.requires_imei and r_item.sale_item.device:
            returned_cogs += r_item.sale_item.device.cost
        else:
            returned_cogs += r_item.quantity * r_item.sale_item.product.average_cost
            
    net_cogs = total_cogs - returned_cogs

    expenses_in_period = Expense.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, shift__start_time__range=(start_dt, end_dt))
    total_expenses = expenses_in_period.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    # أرباح الصيانة (للتقرير المالي فقط - سيتم إعادة حسابها في قسم الصيانة لاحقاً بشكل منفصل)
    pl_tech_labor = RepairTicket.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, created_at__range=(start_dt, end_dt), status__in=['done', 'delivered']).aggregate(total=models.Sum('labor_cost'))['total'] or Decimal('0.00')
    pl_parts_consumed = RepairPartUsed.objects.filter(ticket__branch__in=[request.branch] if request.branch else request.user_allowed_branches, ticket__created_at__range=(start_dt, end_dt), ticket__status__in=['done', 'delivered']).select_related('product')
    pl_parts_cost = Decimal('0.00')
    pl_parts_price = Decimal('0.00')
    for p in pl_parts_consumed:
        pl_parts_cost += p.quantity * p.product.average_cost
        pl_parts_price += p.quantity * p.price
    pl_parts_profit = pl_parts_price - pl_parts_cost
    total_tech_profit = pl_tech_labor + pl_parts_profit

    net_profit = net_sales_revenue - net_cogs - total_expenses + total_tech_profit
    # B. Supplier Balance Statements (Credit balances) - كشف الموردين يعتمد على إجمالي الرصيد الحالي وليس فترة معينة
    suppliers = Contact.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, contact_type='supplier')
    supplier_statements = []
    for sup in suppliers:
        rem = sup.current_balance
        if rem > 0:
            supplier_statements.append({
                'supplier': sup,
                'remaining': rem,
            })
    supplier_statements.sort(key=lambda x: x['remaining'], reverse=True)
    expenses_list = expenses_in_period.select_related('category', 'shift__cashier').order_by('-id')
    # ==========================================
    # 2. SALE REPORTS (تقارير المبيعات)
    # ==========================================
    sales_count = sales_in_period.count()
    sales_total_gross = sales_in_period.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0.00')
    sales_total_discount = sales_in_period.aggregate(total=models.Sum('discount'))['total'] or Decimal('0.00')
    payments_in_period = Payment.objects.filter(invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice__date_created__range=(start_dt, end_dt))
    payment_breakdown = {
        'cash': payments_in_period.filter(payment_method='cash').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
        'card': payments_in_period.filter(payment_method='card').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
        'wallet': payments_in_period.filter(payment_method='wallet').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00'),
    }
    top_selling_items = SaleItem.objects.filter(invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice__date_created__range=(start_dt, end_dt))        .values('product__name')        .annotate(total_qty=models.Sum('quantity'), total_revenue=models.Sum(models.F('quantity') * models.F('unit_price')))        .order_by('-total_qty')[:5]
    # ==========================================
    # 3. PURCHASE REPORTS (تقارير المشتريات)
    # ==========================================
    purchases_in_period = PurchaseInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice_date__range=(start_dt, end_dt))
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
    bulk_stocks = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, quantity__gt=0).select_related('product')
    total_bulk_cost_val = Decimal('0.00')
    total_bulk_selling_val = Decimal('0.00')
    for bs in bulk_stocks:
        total_bulk_cost_val += bs.quantity * bs.product.average_cost
        total_bulk_selling_val += bs.quantity * bs.product.selling_price
    devices_in_stock = Device.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, is_sold=False).select_related('product')
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
    accessories_count = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='accessory', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    spare_parts_count = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='spare_part', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    covers_count = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='cover_screen', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    electrical_count = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='electrical', quantity__gt=0).aggregate(total=models.Sum('quantity'))['total'] or 0
    
    accessories_in_stock = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='accessory', quantity__gt=0).select_related('product', 'warehouse')
    spare_parts_in_stock = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='spare_part', quantity__gt=0).select_related('product', 'warehouse')
    covers_in_stock = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='cover_screen', quantity__gt=0).select_related('product', 'warehouse')
    electrical_in_stock = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, product__product_type='electrical', quantity__gt=0).select_related('product', 'warehouse')
    low_stock_items = Stock.objects.filter(warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches, quantity__lt=5).select_related('product', 'warehouse')

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
    # 5. MAINTENANCE REPORTS (تقارير الصيانة)
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
    # ==========================================
    # 6. CASHIER / SHIFTS REPORT (تقرير الكاشير والورديات)
    # ==========================================
    shifts_in_period = CashShift.objects.filter(
        start_time__range=(start_dt, end_dt)
    ).select_related('cashier').prefetch_related('expenses', 'saleinvoice_set')

    cashier_stats = []
    for shift in shifts_in_period:
        shift_sales = SaleInvoice.objects.filter(shift=shift)
        shift_revenue = shift_sales.aggregate(total=models.Sum('net_amount'))['total'] or Decimal('0.00')
        shift_sales_count = shift_sales.count()
        shift_expenses = shift.expenses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        shift_net = shift_revenue - shift_expenses
        duration = None
        if shift.end_time:
            duration = (shift.end_time - shift.start_time).seconds // 60
        cash_diff = Decimal('0.00')
        if shift.actual_cash is not None and shift.expected_closing_balance is not None:
            cash_diff = shift.actual_cash - shift.expected_closing_balance
        cashier_stats.append({
            'shift': shift,
            'cashier': shift.cashier,
            'revenue': shift_revenue,
            'sales_count': shift_sales_count,
            'expenses': shift_expenses,
            'net': shift_net,
            'duration_min': duration,
            'cash_diff': cash_diff,
            'status': shift.status,
        })

    # Aggregate per cashier
    from django.contrib.auth import get_user_model
    User = get_user_model()
    cashier_summary = {}
    for s in cashier_stats:
        uid = s['cashier'].id if s['cashier'] else 0
        uname = s['cashier'].username if s['cashier'] else 'غير محدد'
        if uid not in cashier_summary:
            cashier_summary[uid] = {
                'username': uname,
                'total_revenue': Decimal('0.00'),
                'total_sales': 0,
                'total_expenses': Decimal('0.00'),
                'shifts_count': 0,
            }
        cashier_summary[uid]['total_revenue'] += s['revenue']
        cashier_summary[uid]['total_sales'] += s['sales_count']
        cashier_summary[uid]['total_expenses'] += s['expenses']
        cashier_summary[uid]['shifts_count'] += 1
    cashier_summary_list = sorted(cashier_summary.values(), key=lambda x: x['total_revenue'], reverse=True)

    # ==========================================
    # 7. TOP CUSTOMERS REPORT (تقرير العملاء المميزين)
    # ==========================================
    top_customers_qs = SaleInvoice.objects.filter(
        branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        date_created__range=(start_dt, end_dt),
        customer__isnull=False
    ).values(
        'customer__id', 'customer__name', 'customer__phone'
    ).annotate(
        total_spent=models.Sum('net_amount'),
        orders_count=models.Count('id'),
        avg_order=models.Avg('net_amount'),
    ).order_by('-total_spent')[:20]

    # Customers with repair tickets (للصيانة أيضاً)
    top_repair_customers = RepairTicket.objects.filter(
        branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        created_at__range=(start_dt, end_dt),
        customer__isnull=False
    ).values(
        'customer__id', 'customer__name', 'customer__phone'
    ).annotate(
        tickets_count=models.Count('id'),
        total_labor=models.Sum('labor_cost'),
    ).order_by('-tickets_count')[:10]

    # ==========================================
    # 8. USED DEVICES P&L (تقرير أرباح الأجهزة المستعملة)
    # ==========================================
    # Devices purchased (used) in period
    used_purchased = Device.objects.filter(
        warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        used_status='purchased',
        created_at__range=(start_dt, end_dt)
    ).select_related('product', 'purchased_from')

    # Devices sold (was used) in period
    used_sold = SaleItem.objects.filter(
        invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        invoice__date_created__range=(start_dt, end_dt),
        device__isnull=False,
        device__condition='used'
    ).select_related('device__product', 'device__purchased_from', 'invoice')

    used_purchased_cost = used_purchased.aggregate(total=models.Sum('cost'))['total'] or Decimal('0.00')
    used_sold_revenue = used_sold.aggregate(
        total=models.Sum(models.F('quantity') * models.F('unit_price'))
    )['total'] or Decimal('0.00')
    used_sold_cost = Decimal('0.00')
    for item in used_sold:
        used_sold_cost += item.device.cost if item.device else Decimal('0.00')
    used_profit = used_sold_revenue - used_sold_cost
    used_margin = (used_profit / used_sold_revenue * 100) if used_sold_revenue > 0 else Decimal('0.00')

    # All used devices currently in stock (not sold)
    used_in_stock = Device.objects.filter(
        warehouse__branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        is_sold=False, condition='used'
    ).select_related('product', 'purchased_from')
    used_in_stock_cost = used_in_stock.aggregate(total=models.Sum('cost'))['total'] or Decimal('0.00')

    # ==========================================
    # 9. WARRANTIES REPORT (تقرير الضمانات)
    # ==========================================
    from datetime import date as date_type
    warranties_all = Warranty.objects.filter(
        invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches
    ).select_related(
        'device__product', 'customer', 'invoice'
    ).order_by('-start_date')

    today_date = timezone.localtime(timezone.now()).date()
    warranties_active = []
    warranties_expiring_soon = []  # expiring within 30 days
    warranties_expired = []

    for w in warranties_all:
        end_date_w = w.start_date + timedelta(days=w.duration_days)
        w.end_date = end_date_w
        days_remaining = (end_date_w - today_date).days
        w.days_remaining = days_remaining
        if days_remaining < 0:
            warranties_expired.append(w)
        elif days_remaining <= 30:
            warranties_expiring_soon.append(w)
        else:
            warranties_active.append(w)

    # ==========================================
    # 10. RECEIVABLES REPORT (تقرير الذمم المدينة)
    # ==========================================
    # جلب جميع الفواتير غير المسددة بالكامل (بدون تقيد بفترة التقرير لأن الدين قائم)
    unpaid_sales = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, 
        payment_method__in=['credit', 'partial']
    ).select_related('customer', 'cashier').order_by('date_created')

    receivables_list = []
    total_receivables = Decimal('0.00')
    for inv in unpaid_sales:
        balance = inv.remaining_amount
        if balance > Decimal('0.01'):
            receivables_list.append({
                'invoice': inv,
                'customer': inv.customer,
                'net_amount': inv.net_amount,
                'paid': inv.paid_amount,
                'balance': balance,
                'date': inv.date_created,
            })
            total_receivables += balance
    receivables_list.sort(key=lambda x: x['balance'], reverse=True)

    # ==========================================
    # 11. TECH PERFORMANCE (تقرير أداء الفنيين التفصيلي)
    # ==========================================
    tech_detailed = []
    technicians = User.objects.filter(
        repairticket__created_at__range=(start_dt, end_dt)
    ).distinct()

    for tech in technicians:
        tech_tickets = RepairTicket.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, 
            technician=tech, created_at__range=(start_dt, end_dt)
        )
        total_tickets = tech_tickets.count()
        done_tickets = tech_tickets.filter(status__in=['done', 'delivered']).count()
        pending_tickets = tech_tickets.filter(status__in=['pending', 'in_progress', 'waiting_parts']).count()
        total_labor_tech = tech_tickets.aggregate(total=models.Sum('labor_cost'))['total'] or Decimal('0.00')
        completion_rate = round((done_tickets / total_tickets * 100), 1) if total_tickets > 0 else 0
        avg_labor = (total_labor_tech / done_tickets) if done_tickets > 0 else Decimal('0.00')
        tech_detailed.append({
            'technician': tech,
            'total_tickets': total_tickets,
            'done_tickets': done_tickets,
            'pending_tickets': pending_tickets,
            'total_labor': total_labor_tech,
            'completion_rate': completion_rate,
            'avg_labor': round(avg_labor, 2),
        })
    tech_detailed.sort(key=lambda x: x['total_labor'], reverse=True)

    # ==========================================
    # 12. DAILY CASH FLOW (تقرير التدفق النقدي اليومي)
    # ==========================================
    from django.db.models.functions import TruncDate
    
    # حركات الخزينة الفعلية (الوارد والمنصرف)
    treasury_tx = TreasuryTransaction.objects.filter(treasury__branch__in=[request.branch] if request.branch else request.user_allowed_branches, 
        date__range=(start_dt, end_dt)
    ).annotate(
        day=TruncDate('date')
    ).values('day', 'transaction_type').annotate(
        total_amount=models.Sum('amount')
    )

    daily_map = {}
    for tx in treasury_tx:
        key = str(tx['day'])
        if key not in daily_map:
            daily_map[key] = {
                'day': tx['day'],
                'revenue': Decimal('0.00'),
                'expenses': Decimal('0.00'),
                'net': Decimal('0.00'),
            }
        if tx['transaction_type'] == 'in':
            daily_map[key]['revenue'] += tx['total_amount']
        else:
            daily_map[key]['expenses'] += tx['total_amount']
            
    for k in daily_map:
        daily_map[k]['net'] = daily_map[k]['revenue'] - daily_map[k]['expenses']
    daily_cashflow = sorted(daily_map.values(), key=lambda x: x['day'])

    # ==========================================
    # 13. CUSTOMER DEBTS (مديونيات العملاء)
    # ==========================================
    # إظهار جميع العملاء الذين لديهم مديونيات قائمة بغض النظر عن تاريخ الفاتورة
    customers = Contact.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, contact_type='customer')
    customer_statements = []
    for cust in customers:
        rem = cust.current_balance
        if rem > 0:
            customer_statements.append({
                'customer': cust,
                'remaining': rem,
            })
    customer_statements.sort(key=lambda x: x['remaining'], reverse=True)

    # ==========================================
    # 14. VAT / TAX REPORT (تقرير الإقرار الضريبي)
    # ==========================================
    sales_tax = Decimal('0.00') # المبيعات لا تحتوي على حقل ضريبة حالياً
    purchases_tax = PurchaseInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, invoice_date__range=(start_dt, end_dt)).aggregate(total=models.Sum('deduction_addition_tax'))['total'] or Decimal('0.00')
    net_tax = sales_tax - purchases_tax

    # ==========================================
    # 15. RETURNS REPORT (تقرير المرتجعات)
    # ==========================================
    from erp.models import SaleReturn, PurchaseReturn
    sales_returns = SaleReturn.objects.filter(sale_invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt)).aggregate(total=models.Sum('refund_amount'))['total'] or Decimal('0.00')
    purchases_returns = PurchaseReturn.objects.filter(purchase_invoice__branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt)).aggregate(total=models.Sum('refund_amount'))['total'] or Decimal('0.00')

    # ==========================================
    # 16. LOYALTY PROGRAM STATS (إحصائيات برنامج الولاء)
    # ==========================================
    loyalty_earned = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt)).aggregate(total=models.Sum('points_earned'))['total'] or 0
    loyalty_redeemed = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt)).aggregate(total=models.Sum('points_redeemed'))['total'] or 0
    loyalty_discount = SaleInvoice.objects.filter(branch__in=[request.branch] if request.branch else request.user_allowed_branches, date_created__range=(start_dt, end_dt)).aggregate(total=models.Sum('points_discount'))['total'] or Decimal('0.00')

    context = {
        'new_reports': {
            'customer_statements': customer_statements,
            'sales_tax': sales_tax,
            'purchases_tax': purchases_tax,
            'net_tax': net_tax,
            'sales_returns': sales_returns,
            'purchases_returns': purchases_returns,
            'loyalty_earned': loyalty_earned,
            'loyalty_redeemed': loyalty_redeemed,
            'loyalty_discount': loyalty_discount,
        },
        'start_date': start_date,
        'end_date': end_date,
        'financials': {
            'total_sales_revenue': total_sales_revenue,
            'total_sales_returns': total_sales_returns_amount,
            'net_sales_revenue': net_sales_revenue,
            'total_cogs': total_cogs,
            'net_cogs': net_cogs,
            'returned_cogs': returned_cogs,
            'total_expenses': total_expenses,
            'tech_profit': total_tech_profit,
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
            'net_after_returns': net_sales_revenue,
            'returns_count': sales_returns_in_period.count(),
            'returns_amount': total_sales_returns_amount,
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
        },
        # ── التقارير الجديدة ──
        'cashier_report': {
            'shifts': cashier_stats,
            'summary': cashier_summary_list,
            'total_shifts': len(cashier_stats),
        },
        'customers_report': {
            'top_buyers': top_customers_qs,
            'top_repair': top_repair_customers,
        },
        'used_devices_report': {
            'purchased_count': used_purchased.count(),
            'purchased_cost': used_purchased_cost,
            'sold_count': used_sold.count(),
            'sold_revenue': used_sold_revenue,
            'sold_cost': used_sold_cost,
            'profit': used_profit,
            'margin': round(used_margin, 1),
            'in_stock': used_in_stock,
            'in_stock_cost': used_in_stock_cost,
            'sold_list': used_sold,
        },
        'warranty_report': {
            'active': warranties_active,
            'expiring_soon': warranties_expiring_soon,
            'expired': warranties_expired,
            'total': len(warranties_active) + len(warranties_expiring_soon) + len(warranties_expired),
        },
        'receivables_report': {
            'list': receivables_list[:50],
            'total': total_receivables,
            'count': len(receivables_list),
        },
        'tech_report': {
            'technicians': tech_detailed,
        },
        'cashflow_report': {
            'daily': daily_cashflow,
            'labels': [str(d['day']) for d in daily_cashflow],
            'revenues': [float(d['revenue']) for d in daily_cashflow],
            'expenses': [float(d['expenses']) for d in daily_cashflow],
            'nets': [float(d['net']) for d in daily_cashflow],
        },
    }
    if request.headers.get('HX-Request'):
        target = request.headers.get('HX-Target')
        if target == 'inventory-products-table-container':
            return render(request, 'erp/includes/reports_inventory_table.html', context)
        elif target == 'maintenance-tickets-table-container':
            return render(request, 'erp/includes/reports_maintenance_table.html', context)
    return render(request, 'erp/reports.html', context)

@login_required
def notification_settings(request):
    """
    صفحة إعدادات الإشعارات — رقم الواتساب + قوالب الرسائل.
    """
    from erp.models import NotificationSettings
    settings_obj = NotificationSettings.get_settings()

    if request.method == 'POST':
        settings_obj.whatsapp_enabled = 'whatsapp_enabled' in request.POST
        settings_obj.sender_phone = request.POST.get('sender_phone', '').strip()
        settings_obj.branch_name = request.POST.get('branch_name', '').strip()
        settings_obj.delay_min_seconds = int(request.POST.get('delay_min_seconds', 15))
        settings_obj.delay_max_seconds = int(request.POST.get('delay_max_seconds', 45))
        for status_key in ['pending', 'in_progress', 'waiting_parts', 'done', 'delivered']:
            enabled_field = f'msg_{status_key}_enabled'
            template_field = f'msg_{status_key}'
            setattr(settings_obj, enabled_field, enabled_field in request.POST)
            setattr(settings_obj, template_field, request.POST.get(template_field, '').strip())
        settings_obj.save()
        messages.success(request, 'تم حفظ إعدادات الإشعارات بنجاح.')
        return redirect('erp:notification_settings')

    return render(request, 'erp/notification_settings.html', {'settings': settings_obj})


@login_required
def notifications_dashboard(request):
    """
    لوحة سجل الإشعارات المرسلة / الفاشلة.
    """
    from erp.models import NotificationLog, NotificationSettings
    from django.core.paginator import Paginator
    status_filter = request.GET.get('status', '')
    logs_qs = NotificationLog.objects.select_related('customer', 'ticket').order_by('-sent_at')
    if status_filter:
        logs_qs = logs_qs.filter(status=status_filter)
    paginator = Paginator(logs_qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    stats = {
        'total':   NotificationLog.objects.count(),
        'sent':    NotificationLog.objects.filter(status='sent').count(),
        'failed':  NotificationLog.objects.filter(status='failed').count(),
        'queued':  NotificationLog.objects.filter(status='queued').count(),
        'skipped': NotificationLog.objects.filter(status='skipped').count(),
    }
    settings_obj = NotificationSettings.get_settings()
    return render(request, 'erp/notifications_dashboard.html', {
        'logs': page, 'stats': stats,
        'status_filter': status_filter, 'settings': settings_obj,
    })


@login_required
@require_POST
def retry_notification(request, log_id):
    """
    إعادة إرسال إشعار فاشل.
    """
    from django_q.tasks import async_task
    from erp.models import NotificationLog
    log = get_object_or_404(NotificationLog, id=log_id)
    log.status = 'queued'
    log.error_message = None
    log.save(update_fields=['status', 'error_message'])
    async_task(
        'erp.tasks.send_whatsapp_notification',
        log_id=log.id,
        task_name=f"retry_whatsapp_log_{log.id}",
    )
    return redirect('erp:notifications_dashboard')

# ==========================================
# 11. شؤون الموظفين والرواتب (HR & Payroll)
# ==========================================
from erp.models import EmployeeProfile, Attendance, Payroll
from erp.forms import EmployeeProfileForm
import math

@login_required
@permission_required('erp.view_employeeprofile', raise_exception=True)
def employee_list(request):
    employees = EmployeeProfile.objects.all().select_related('user')
    return render(request, 'erp/hr/employee_list.html', {'employees': employees})

@login_required
@permission_required('erp.add_employeeprofile', raise_exception=True)
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeProfileForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة ملف الموظف بنجاح.")
            return redirect('erp:employee_list')
    else:
        form = EmployeeProfileForm()
    return render(request, 'erp/hr/employee_form.html', {'form': form, 'title': 'إضافة موظف جديد'})

@login_required
@permission_required('erp.change_employeeprofile', raise_exception=True)
def employee_edit(request, pk):
    employee = get_object_or_404(EmployeeProfile, pk=pk)
    if request.method == 'POST':
        form = EmployeeProfileForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل بيانات الموظف بنجاح.")
            return redirect('erp:employee_list')
    else:
        form = EmployeeProfileForm(instance=employee)
    return render(request, 'erp/hr/employee_form.html', {'form': form, 'title': 'تعديل ملف موظف', 'employee': employee})

@login_required
def attendance_dashboard(request):
    # لوحة البصمة الخاصة بالموظف
    try:
        profile = request.user.employee_profile
    except EmployeeProfile.DoesNotExist:
        messages.error(request, "ليس لديك ملف موظف لتسجيل الحضور.")
        return redirect('erp:dashboard')
    
    today = timezone.now().date()
    attendance = Attendance.objects.filter(employee=profile, date=today).first()
    
    # إعدادات المحل
    store_setting = StoreSetting.objects.first()
    
    context = {
        'profile': profile,
        'attendance': attendance,
        'store_setting': store_setting,
    }
    return render(request, 'erp/hr/attendance.html', context)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@login_required
@require_POST
def api_attendance_check(request):
    try:
        profile = request.user.employee_profile
    except EmployeeProfile.DoesNotExist:
        return JsonResponse({'error': 'ملف الموظف غير موجود.'}, status=400)
        
    action = request.POST.get('action') # 'check_in' or 'check_out'
    user_lat = request.POST.get('latitude')
    user_lon = request.POST.get('longitude')
    
    if not user_lat or not user_lon:
        return JsonResponse({'error': 'لم يتم العثور على إحداثيات الموقع.'}, status=400)
        
    if not profile.active_branch:
        return JsonResponse({'error': 'لم يتم تعيينك على أي فرع نشط حالياً.'}, status=400)
        
    branch = profile.active_branch
    if not branch.latitude or not branch.longitude:
        return JsonResponse({'error': f'لم يتم ضبط إحداثيات الموقع الجغرافي للفرع: {branch.name}. يرجى مراجعة الإدارة.'}, status=400)
        
    distance = haversine(float(user_lat), float(user_lon), float(branch.latitude), float(branch.longitude))
    allowed_radius = branch.allowed_radius or 50
    
    if distance > allowed_radius:
        return JsonResponse({'error': f'أنت بعيد جداً عن فرع {branch.name}. المسافة: {int(distance)} متر (المسموح {allowed_radius} متر).'}, status=400)
        
    today = timezone.now().date()
    now_time = timezone.now()
    attendance, created = Attendance.objects.get_or_create(employee=profile, date=today)
    
    if action == 'check_in':
        if attendance.check_in:
            return JsonResponse({'error': 'لقد قمت بتسجيل الحضور مسبقاً اليوم.'}, status=400)
        attendance.check_in = now_time
        # حساب التأخير
        if profile.shift_start_time:
            start_datetime = timezone.make_aware(timezone.datetime.combine(today, profile.shift_start_time))
            if now_time > start_datetime:
                delay_secs = (now_time - start_datetime).total_seconds()
                attendance.delay_hours = Decimal(delay_secs / 3600.0).quantize(Decimal('0.01'))
        attendance.save()
        return JsonResponse({'status': 'success', 'message': 'تم تسجيل الحضور بنجاح.'})
        
    elif action == 'check_out':
        if not attendance.check_in:
            return JsonResponse({'error': 'يجب تسجيل الحضور أولاً.'}, status=400)
        if attendance.check_out:
            return JsonResponse({'error': 'لقد قمت بتسجيل الانصراف مسبقاً اليوم.'}, status=400)
        attendance.check_out = now_time
        # حساب الإضافي
        if profile.shift_end_time:
            end_datetime = timezone.make_aware(timezone.datetime.combine(today, profile.shift_end_time))
            if now_time > end_datetime:
                overtime_secs = (now_time - end_datetime).total_seconds()
                attendance.overtime_hours = Decimal(overtime_secs / 3600.0).quantize(Decimal('0.01'))
        attendance.save()
        return JsonResponse({'status': 'success', 'message': 'تم تسجيل الانصراف بنجاح.'})
        
    return JsonResponse({'error': 'إجراء غير معروف.'}, status=400)

@login_required
@permission_required('erp.view_payroll', raise_exception=True)
def payroll_list(request):
    payrolls = Payroll.objects.all().order_by('-year', '-month')
    treasuries = Treasury.objects.filter(is_active=True)
    return render(request, 'erp/hr/payroll_list.html', {'payrolls': payrolls, 'treasuries': treasuries})

@login_required
@permission_required('erp.add_payroll', raise_exception=True)
@require_POST
def payroll_generate(request):
    month = request.POST.get('month')
    year = request.POST.get('year')
    if not month or not year:
        messages.error(request, "يجب تحديد الشهر والسنة.")
        return redirect('erp:payroll_list')
        
    month = int(month)
    year = int(year)
    
    employees = EmployeeProfile.objects.filter(is_active=True)
    generated = 0
    for emp in employees:
        # جمع الحضور في هذا الشهر
        attendances = Attendance.objects.filter(employee=emp, date__year=year, date__month=month)
        
        total_delay = sum(a.delay_hours for a in attendances)
        total_overtime = sum(a.overtime_hours for a in attendances)
        total_worked_hours = 0
        for a in attendances:
            if a.check_in and a.check_out:
                diff = (a.check_out - a.check_in).total_seconds() / 3600.0
                total_worked_hours += Decimal(diff)
                
        # حساب الراتب العادي (حسب الراتب الأساسي، أو حسب الساعات)
        # إذا كان لديه راتب أساسي، نستخدمه، وإلا نضرب الساعات في السعر
        if emp.base_salary > 0:
            base_pay = emp.base_salary
        else:
            base_pay = Decimal(total_worked_hours) * emp.hourly_rate
            
        overtime_pay = Decimal(total_overtime) * emp.overtime_per_hour
        deductions = Decimal(total_delay) * emp.deduction_per_hour
        
        net_salary = base_pay + overtime_pay - deductions
        
        payroll, created = Payroll.objects.update_or_create(
            employee=emp, month=month, year=year,
            defaults={
                'total_worked_hours': total_worked_hours,
                'total_delay_hours': total_delay,
                'total_overtime_hours': total_overtime,
                'base_pay': base_pay,
                'overtime_pay': overtime_pay,
                'deductions': deductions,
                'net_salary': net_salary if net_salary > 0 else 0
            }
        )
        if created:
            generated += 1
            
    messages.success(request, f"تم إنشاء/تحديث {generated} مسير راتب لشهر {month}/{year}.")
    return redirect('erp:payroll_list')

@login_required
@permission_required('erp.change_payroll', raise_exception=True)
@require_POST
def payroll_pay(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    treasury_id = request.POST.get('treasury_id')
    
    if payroll.is_paid:
        messages.error(request, "تم صرف هذا الراتب مسبقاً.")
        return redirect('erp:payroll_list')
        
    if not treasury_id:
        messages.error(request, "يجب تحديد الخزينة لصرف الراتب.")
        return redirect('erp:payroll_list')
        
    try:
        with transaction.atomic():
            treasury = Treasury.objects.select_for_update().get(id=treasury_id, is_active=True)
            if treasury.balance < payroll.net_salary:
                messages.error(request, f"رصيد الخزينة المحددة لا يكفي ({treasury.balance} ج.م متوفر، مطلوب {payroll.net_salary} ج.م).")
                return redirect('erp:payroll_list')
                
            treasury.record_transaction(payroll.net_salary, 'out', f'صرف راتب الموظف {payroll.employee.user.username}', request.user)
            
            payroll.is_paid = True
            payroll.paid_at = timezone.now()
            payroll.save()
            
            messages.success(request, f"تم صرف راتب الموظف {payroll.employee} لشهر {payroll.month} بنجاح.")
    except Treasury.DoesNotExist:
        messages.error(request, "الخزينة المحددة غير صالحة.")
        
    return redirect('erp:payroll_list')

# ==========================================
# 12. المرتجعات (Returns)
# ==========================================
from erp.models import SaleReturn, SaleReturnItem, PurchaseReturn, PurchaseReturnItem

@login_required
@permission_required('erp.add_saleinvoice', raise_exception=True)
@require_specific_branch
def sale_return_create(request, pk):
    sale_invoice = get_object_or_404(SaleInvoice, pk=pk)
    # التحقق من عدم عمل مرتجع كامل مسبقا
    if request.method == 'POST':
        treasury_id = request.POST.get('treasury_id')
        refund_amount = Decimal(request.POST.get('refund_amount', 0))
        debt_reduction = Decimal(request.POST.get('debt_reduction', 0))
        notes = request.POST.get('notes', '')
        
        if not treasury_id and refund_amount > 0:
            messages.error(request, "يجب تحديد الخزينة لخصم قيمة المرتجع.")
            return redirect('erp:sale_detail', pk=pk)
            
        try:
            with transaction.atomic():
                if treasury_id:
                    treasury = Treasury.objects.select_for_update().get(pk=treasury_id)
                    if refund_amount > 0 and treasury.balance < refund_amount:
                        messages.error(request, f"لا يوجد رصيد كافٍ في الخزينة المحددة. (متوفر: {treasury.balance})")
                        return redirect('erp:sale_detail', pk=pk)
                else:
                    # If refund_amount is 0, we can use the first active treasury as a placeholder or null if allowed.
                    # Since treasury is required on SaleReturn model (PROTECT), we must supply one.
                    treasury = Treasury.objects.filter(is_active=True).first()
                    if not treasury:
                        raise ValueError("يجب تفعيل خزينة واحدة على الأقل في النظام.")
                
                # إنشاء فاتورة المرتجع
                sale_return = SaleReturn.objects.create(
                    sale_invoice=sale_invoice,
                    treasury=treasury,
                    created_by=request.user,
                    refund_amount=refund_amount,
                    debt_reduction=debt_reduction,
                    notes=notes
                )
                
                # معالجة البنود
                has_items = False
                for item in sale_invoice.items.all():
                    qty_to_return = int(request.POST.get(f'return_qty_{item.id}', 0))
                    if qty_to_return > 0:
                        if qty_to_return > item.quantity:
                            raise ValueError(f"الكمية المرتجعة للصنف {item.product.name} أكبر من المباعة.")
                        
                        SaleReturnItem.objects.create(
                            return_invoice=sale_return,
                            sale_item=item,
                            quantity=qty_to_return
                        )
                        
                        # تحديث المخزون
                        stock, created = Stock.objects.get_or_create(
                            product=item.product,
                            warehouse=item.warehouse,
                            defaults={'quantity': 0}
                        )
                        stock.quantity += qty_to_return
                        stock.save()
                        
                        # تحديث حالة الجهاز لو كان موبايل
                        if item.device:
                            item.device.is_sold = False
                            item.device.warehouse = item.warehouse
                            item.device.save()
                            
                        has_items = True
                        
                if not has_items:
                    raise ValueError("يجب تحديد صنف واحد على الأقل للاسترجاع بكمية أكبر من صفر.")
                    
                # خصم المبلغ من الخزينة
                if refund_amount > 0:
                    treasury.record_transaction(refund_amount, 'out', f'مرتجع مبيعات للفاتورة الأصلية {original_invoice.id}', request.user)
                    
                messages.success(request, "تم تسجيل مرتجع المبيعات بنجاح واسترداد المخزون.")
                return redirect('erp:sale_detail', pk=pk)
                
        except ValueError as e:
            messages.error(request, str(e))
        except Treasury.DoesNotExist:
            messages.error(request, "الخزينة المحددة غير صالحة.")
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {str(e)}")
            
    treasuries = Treasury.objects.filter(is_active=True)
    return render(request, 'erp/returns/sale_return_create.html', {'sale_invoice': sale_invoice, 'treasuries': treasuries})

@login_required
@permission_required('erp.add_purchaseinvoice', raise_exception=True)
@require_specific_branch
def purchase_return_create(request, pk):
    purchase_invoice = get_object_or_404(PurchaseInvoice, pk=pk)
    
    if request.method == 'POST':
        treasury_id = request.POST.get('treasury_id')
        refund_amount = Decimal(request.POST.get('refund_amount', 0))
        debt_reduction = Decimal(request.POST.get('debt_reduction', 0))
        notes = request.POST.get('notes', '')
        
        if not treasury_id and refund_amount > 0:
            messages.error(request, "يجب تحديد الخزينة لإيداع القيمة المستردة.")
            return redirect('erp:purchase_detail', pk=pk)
            
        try:
            with transaction.atomic():
                if treasury_id:
                    treasury = Treasury.objects.select_for_update().get(pk=treasury_id)
                else:
                    treasury = Treasury.objects.filter(is_active=True).first()
                    if not treasury:
                        raise ValueError("يجب تفعيل خزينة واحدة على الأقل في النظام.")
                
                # إنشاء المرتجع
                purchase_return = PurchaseReturn.objects.create(
                    purchase_invoice=purchase_invoice,
                    treasury=treasury,
                    created_by=request.user,
                    refund_amount=refund_amount,
                    debt_reduction=debt_reduction,
                    notes=notes
                )
                
                has_items = False
                for item in purchase_invoice.items.all():
                    qty_to_return = int(request.POST.get(f'return_qty_{item.id}', 0))
                    if qty_to_return > 0:
                        if qty_to_return > item.quantity:
                            raise ValueError(f"الكمية المرتجعة للصنف {item.product.name} أكبر من المشتراة.")
                        
                        PurchaseReturnItem.objects.create(
                            return_invoice=purchase_return,
                            purchase_item=item,
                            quantity=qty_to_return
                        )
                        
                        # تحديث المخزون (تخفيض)
                        stock = Stock.objects.get(product=item.product, warehouse=item.warehouse)
                        if stock.quantity < qty_to_return:
                            raise ValueError(f"رصيد المخزون للصنف {item.product.name} أقل من الكمية المرتجعة، لا يمكن إرجاعها الآن.")
                            
                        stock.quantity -= qty_to_return
                        stock.save()
                        has_items = True
                        
                if not has_items:
                    raise ValueError("يجب تحديد صنف واحد على الأقل للاسترجاع بكمية أكبر من صفر.")
                    
                # إضافة المبلغ للخزينة
                if refund_amount > 0:
                    treasury.record_transaction(refund_amount, 'in', f'مرتجع مشتريات للفاتورة الأصلية {original_invoice.id}', request.user)
                    
                messages.success(request, "تم تسجيل مرتجع المشتريات بنجاح وتخفيض المخزون وإيداع المبلغ في الخزينة.")
                return redirect('erp:purchase_detail', pk=pk)
                
        except ValueError as e:
            messages.error(request, str(e))
        except Treasury.DoesNotExist:
            messages.error(request, "الخزينة المحددة غير صالحة.")
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {str(e)}")
            
    treasuries = Treasury.objects.filter(is_active=True)
    return render(request, 'erp/returns/purchase_return_create.html', {'purchase_invoice': purchase_invoice, 'treasuries': treasuries})

@login_required
def treasury_transactions_report(request):
    if not request.user.is_staff and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("عذراً، يجب أن تكون مشرفاً أو مديراً للوصول لتقرير حركات الخزينة.")
    
    from erp.models import Treasury, TreasuryTransaction
    from django.utils import timezone
    from datetime import datetime, timedelta
    from django.db import models

    # فلاتر البحث
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    treasury_id = request.GET.get('treasury_id')

    today = timezone.localtime(timezone.now()).date()
    default_start = today - timedelta(days=30)
    
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
            end_date = today
    else:
        end_date = today

    # الاستعلام الأساسي
    transactions = TreasuryTransaction.objects.filter(
        treasury__branch__in=[request.branch] if request.branch else request.user_allowed_branches,
        date__date__gte=start_date,
        date__date__lte=end_date
    )

    if treasury_id:
        transactions = transactions.filter(treasury_id=treasury_id)

    # حساب المجاميع
    total_in = transactions.filter(transaction_type='in').aggregate(total=models.Sum('amount'))['total'] or 0
    total_out = transactions.filter(transaction_type='out').aggregate(total=models.Sum('amount'))['total'] or 0
    net_movement = total_in - total_out

    context = {
        'transactions': transactions.select_related('treasury', 'user').order_by('-date'),
        'treasuries': Treasury.objects.filter(is_active=True, branch__in=[request.branch] if request.branch else request.user_allowed_branches),
        'start_date': start_date,
        'end_date': end_date,
        'selected_treasury': int(treasury_id) if treasury_id else None,
        'total_in': total_in,
        'total_out': total_out,
        'net_movement': net_movement,
    }
    return render(request, 'erp/treasury_report.html', context)



@login_required
def achievements_report(request):
    if not request.user.is_staff and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("عذراً، يجب أن تكون مشرفاً أو مديراً للوصول لتقرير المحققات.")
        
    from erp.models import SaleInvoice, SaleItem, CommissionRule, SalesTarget, Product
    from django.db.models import Sum, F
    from django.utils import timezone
    from datetime import datetime, timedelta
    
    period = request.GET.get('period', 'monthly')
    target_date_str = request.GET.get('target_date')
    
    today = timezone.localtime(timezone.now()).date()
    
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = today
    else:
        target_date = today
        
    if period == 'daily':
        start_date = target_date
        end_date = target_date
    elif period == 'monthly':
        start_date = target_date.replace(day=1)
        if target_date.month == 12:
            end_date = target_date.replace(year=target_date.year+1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = target_date.replace(month=target_date.month+1, day=1) - timedelta(days=1)
    else: # yearly
        start_date = target_date.replace(month=1, day=1)
        end_date = target_date.replace(month=12, day=31)
        
    # جلب قواعد العمولة المتاحة في قاموس لسرعة الوصول
    rules = {rule.product_type: rule for rule in CommissionRule.objects.all()}
    
    from django.contrib.auth.models import User
    cashiers = User.objects.filter(is_active=True)
    
    report_data = []
    
    for cashier in cashiers:
        # حساب مبيعات هذا الكاشير في الفترة المحددة
        sales_invoices = SaleInvoice.objects.filter(
            cashier=cashier,
            date_created__date__gte=start_date,
            date_created__date__lte=end_date
        )
        
        # إذا لم يكن لديه مبيعات ولا تارجت، نتخطاه (أو يمكن إظهاره إذا أردنا)
        # جلب التارجت إن وجد
        target = SalesTarget.objects.filter(user=cashier, period=period, date__year=target_date.year, date__month=target_date.month if period in ['daily', 'monthly'] else 1).first()
        if period == 'daily' and target:
            # للتارجت اليومي نتأكد من تطابق اليوم أيضاً
            target = SalesTarget.objects.filter(user=cashier, period=period, date=target_date).first()
            
        if not sales_invoices.exists() and not target:
            continue
            
        # تجميع مبيعات الكاشير حسب نوع الصنف
        items = SaleItem.objects.filter(invoice__in=sales_invoices).values(
            product_type=F('product__product_type')
        ).annotate(
            total_sales=Sum(F('quantity') * F('unit_price'))
        )
        
        categories_data = []
        total_commission = 0
        total_sales_amount = 0
        
        for item in items:
            ptype = item['product_type']
            sales = item['total_sales'] or 0
            total_sales_amount += sales
            
            comm = 0
            if ptype in rules:
                rule = rules[ptype]
                if rule.sales_milestone > 0:
                    milestones_achieved = int(sales // rule.sales_milestone)
                    comm = milestones_achieved * rule.commission_amount
                    total_commission += comm
            
            # نحتاج اسم النوع بدلاً من الكود
            ptype_display = dict(Product.PRODUCT_TYPES).get(ptype, ptype)
            categories_data.append({
                'type': ptype_display,
                'sales': sales,
                'commission': comm
            })
            
        progress = 0
        if target and target.target_amount > 0:
            progress = min(100, int((total_sales_amount / target.target_amount) * 100))
            
        report_data.append({
            'cashier': cashier,
            'categories': categories_data,
            'total_sales': total_sales_amount,
            'total_commission': total_commission,
            'target': target.target_amount if target else 0,
            'progress': progress
        })
        
    context = {
        'report_data': report_data,
        'period': period,
        'target_date': target_date,
        'start_date': start_date,
        'end_date': end_date
    }
    return render(request, 'erp/achievements_report.html', context)


@login_required
@require_specific_branch
def targets_manage(request):
    if not request.user.is_staff and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("عذراً، هذه الصفحة مخصصة للمديرين فقط.")
        
    from erp.forms import CommissionRuleForm, SalesTargetForm
    from erp.models import CommissionRule, SalesTarget
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_commission':
            form = CommissionRuleForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "تم إضافة قاعدة العمولة بنجاح!")
            else:
                messages.error(request, "تأكد من صحة البيانات المدخلة (قد تكون الفئة مسجلة مسبقاً).")
                
        elif action == 'delete_commission':
            rule_id = request.POST.get('rule_id')
            CommissionRule.objects.filter(id=rule_id).delete()
            messages.success(request, "تم حذف قاعدة العمولة.")
            
        elif action == 'add_target':
            form = SalesTargetForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "تم إضافة التارجت بنجاح!")
            else:
                messages.error(request, "خطأ: تأكد من عدم وجود تارجت مسجل لنفس الموظف ونفس الفترة مسبقاً.")
                
        elif action == 'delete_target':
            target_id = request.POST.get('target_id')
            SalesTarget.objects.filter(id=target_id).delete()
            messages.success(request, "تم حذف التارجت.")
            
        return redirect('erp:targets_manage')
        
    rules = CommissionRule.objects.all()
    targets = SalesTarget.objects.all().order_by('-date')
    
    context = {
        'rules': rules,
        'targets': targets,
        'commission_form': CommissionRuleForm(),
        'target_form': SalesTargetForm()
    }
    return render(request, 'erp/targets_manage.html', context)


@login_required
def system_audit_log(request):
    if not request.user.is_staff and not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("عذراً، يجب أن تكون مديراً للوصول لسجل النظام.")
        
    from erp.models import AuditLog
    from django.core.paginator import Paginator
    
    logs_list = AuditLog.objects.all().select_related('user')
    
    # الفلترة
    user_id = request.GET.get('user')
    action = request.GET.get('action')
    model_name = request.GET.get('model_name')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if user_id:
        logs_list = logs_list.filter(user_id=user_id)
    if action:
        logs_list = logs_list.filter(action=action)
    if model_name:
        logs_list = logs_list.filter(model_name__icontains=model_name)
    if date_from:
        logs_list = logs_list.filter(timestamp__date__gte=date_from)
    if date_to:
        logs_list = logs_list.filter(timestamp__date__lte=date_to)
        
    paginator = Paginator(logs_list, 50)
    page_number = request.GET.get('page')
    logs = paginator.get_page(page_number)
    
    from django.contrib.auth.models import User
    users = User.objects.all()
    
    context = {
        'logs': logs,
        'users': users,
    }
    return render(request, 'erp/audit_log.html', context)


@login_required
def verify_gift_card(request):
    code = request.GET.get('code', '').strip()
    if not code:
        return JsonResponse({'valid': False, 'message': 'لم يتم إدخال كود.'})
    try:
        from erp.models import GiftCard
        card = GiftCard.objects.get(code=code, is_active=True)
        from django.utils.timezone import now
        if card.expires_at and card.expires_at < now().date():
            return JsonResponse({'valid': False, 'message': 'بطاقة الهدية منتهية الصلاحية.'})
        return JsonResponse({'valid': True, 'balance': float(card.current_balance), 'message': f'تم تفعيل البطاقة. الرصيد: {card.current_balance} ج.م'})
    except Exception:
        return JsonResponse({'valid': False, 'message': 'كود بطاقة الهدية غير صحيح أو غير مفعل.'})


@login_required
@require_specific_branch
def gift_cards_manage(request):
    # Only for staff/superusers
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'غير مصرح لك بالدخول لهذه الصفحة.')
        return redirect('erp:dashboard')
        
    from erp.models import GiftCard
    import uuid
    from django.contrib import messages
    from django.shortcuts import redirect, render
    
    if request.method == 'POST':
        if 'issue_card' in request.POST:
            amount = float(request.POST.get('amount', 0))
            if amount > 0:
                # Generate unique code
                code = str(uuid.uuid4().hex)[:10].upper()
                GiftCard.objects.create(
                    code=code,
                    initial_balance=amount,
                    current_balance=amount,
                    is_active=True
                )
                messages.success(request, f'تم إصدار بطاقة هدية جديدة بنجاح! الكود: {code}')
            else:
                messages.error(request, 'يرجى إدخال مبلغ صحيح.')
        elif 'toggle_status' in request.POST:
            card_id = request.POST.get('card_id')
            try:
                card = GiftCard.objects.get(id=card_id)
                card.is_active = not card.is_active
                card.save()
                status = "مفعلة" if card.is_active else "موقوفة"
                messages.success(request, f'تم تغيير حالة البطاقة {card.code} إلى {status}.')
            except GiftCard.DoesNotExist:
                messages.error(request, 'البطاقة غير موجودة.')
        return redirect('erp:gift_cards_manage')
        
    cards = GiftCard.objects.all().order_by('-created_at')
    
    context = {
        'cards': cards
    }
    return render(request, 'erp/gift_cards.html', context)


@login_required
@require_specific_branch
def print_gift_card(request, pk):
    # Only for staff/superusers
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'غير مصرح لك بالدخول لهذه الصفحة.')
        return redirect('erp:dashboard')
        
    from erp.models import GiftCard
    from django.shortcuts import get_object_or_404
    card = get_object_or_404(GiftCard, id=pk)
    
    return render(request, 'erp/print_gift_card.html', {'card': card})


@login_required
def check_warranty_imei(request):
    imei = request.GET.get('imei', '').strip()
    if not imei:
        return JsonResponse({'found': False})
        
    from erp.models import RepairTicket
    from django.utils.timezone import now
    import datetime
    
    # Find the most recent delivered ticket for this IMEI
    ticket = RepairTicket.objects.filter(device_imei=imei, status='delivered').order_by('-created_at').first()
    
    if ticket and ticket.warranty_days > 0:
        # Check if still in warranty
        days_passed = (now().date() - ticket.created_at.date()).days
        if days_passed <= ticket.warranty_days:
            return JsonResponse({
                'found': True,
                'in_warranty': True,
                'ticket_id': ticket.id,
                'days_passed': days_passed,
                'warranty_days': ticket.warranty_days,
                'message': f'هذا الجهاز تمت صيانته منذ {days_passed} يوم (تذكرة #{ticket.id}) ولا يزال داخل فترة الضمان ({ticket.warranty_days} يوم).'
            })
        else:
            return JsonResponse({
                'found': True,
                'in_warranty': False,
                'ticket_id': ticket.id,
                'message': f'الجهاز مسجل في تذكرة سابقة #{ticket.id} ولكن فترة الضمان انتهت.'
            })
            
    return JsonResponse({'found': False})


@login_required
def imei_lifecycle_report(request):
    imei = request.GET.get('imei', '').strip()
    if not imei:
        return JsonResponse({'error': 'No IMEI provided'})
    
    from erp.models import Device, SaleItem, RepairTicket, SaleReturnItem, PurchaseReturnItem
    
    lifecycle = []
    
    # 1. Device Purchase / Entry
    devices = Device.objects.filter(imei=imei).select_related('purchased_from', 'product')
    for d in devices:
        supplier_name = d.purchased_from.name if d.purchased_from else 'غير محدد'
        lifecycle.append({
            'date': d.created_at,
            'event': 'شراء / دخول المخزن',
            'details': f'دخل المخزن عبر المورد: {supplier_name} بتكلفة {d.cost}',
            'product': d.product.name
        })
        
    # 2. Sales
    sales = SaleItem.objects.filter(device__imei=imei).select_related('invoice', 'invoice__customer')
    for s in sales:
        cust_name = s.invoice.customer.name if s.invoice.customer else 'عميل نقدي'
        lifecycle.append({
            'date': s.invoice.date_created,
            'event': 'بيع للعميل',
            'details': f'تم البيع للعميل: {cust_name} بفاتورة #{s.invoice.id} بقيمة {s.unit_price}',
            'product': s.product.name
        })
        
    # 3. Sale Returns
    sale_returns = SaleReturnItem.objects.filter(sale_item__device__imei=imei).select_related('return_invoice')
    for sr in sale_returns:
        lifecycle.append({
            'date': sr.return_invoice.date_created,
            'event': 'مرتجع مبيعات',
            'details': f'تم استرجاع الجهاز في فاتورة مرتجع #{sr.return_invoice.id}',
            'product': sr.sale_item.product.name
        })

    # 4. Repairs
    repairs = RepairTicket.objects.filter(device_imei=imei).select_related('customer')
    for r in repairs:
        lifecycle.append({
            'date': r.created_at,
            'event': 'دخول صيانة',
            'details': f'دخل صيانة بتذكرة #{r.id} وحالتها الحالية ({r.get_status_display()}) بتكلفة {r.total_cost}',
            'product': r.device_model
        })

    lifecycle.sort(key=lambda x: x['date'])
    
    # Format dates
    for item in lifecycle:
        item['date_str'] = item['date'].strftime('%Y-%m-%d %H:%M')
        
    return JsonResponse({'status': 'success', 'history': lifecycle})
