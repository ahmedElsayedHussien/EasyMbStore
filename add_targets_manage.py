import os

# 1. Update forms.py
forms_path = 'erp/forms.py'
with open(forms_path, 'a', encoding='utf-8') as f:
    f.write('''

from .models import CommissionRule, SalesTarget
class CommissionRuleForm(forms.ModelForm):
    class Meta:
        model = CommissionRule
        fields = ['product_type', 'sales_milestone', 'commission_amount']

class SalesTargetForm(forms.ModelForm):
    class Meta:
        model = SalesTarget
        fields = ['user', 'period', 'target_amount', 'date']
''')

# 2. Update views.py
views_path = 'erp/views.py'
with open(views_path, 'a', encoding='utf-8') as f:
    f.write('''

@login_required
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
''')
