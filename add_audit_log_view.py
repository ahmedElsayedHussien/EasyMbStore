import os

filepath = 'erp/views.py'
with open(filepath, 'a', encoding='utf-8') as f:
    f.write('''

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
''')
print("system_audit_log appended successfully.")
