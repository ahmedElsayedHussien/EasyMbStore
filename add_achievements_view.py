import os

filepath = 'erp/views.py'
with open(filepath, 'a', encoding='utf-8') as f:
    f.write('''

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
''')
print("View appended successfully")
