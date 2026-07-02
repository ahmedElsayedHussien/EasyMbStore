import threading
import random
from django.utils.timezone import now
from datetime import timedelta

_thread_locals = threading.local()

def cleanup_old_audit_logs():
    try:
        from erp.models import AuditLog
        one_year_ago = now() - timedelta(days=365)
        AuditLog.objects.filter(timestamp__lt=one_year_ago).delete()
    except Exception:
        pass

def get_current_user():
    return getattr(_thread_locals, 'user', None)

def get_current_ip():
    return getattr(_thread_locals, 'ip', None)

class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            from django.db import connection
            if connection.schema_name == 'public':
                return self.get_response(request)
        except Exception:
            pass
            
        # تخزين المستخدم الحالي
        if hasattr(request, 'user') and request.user.is_authenticated:
            _thread_locals.user = request.user
        else:
            _thread_locals.user = None
            
        # تخزين الـ IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        _thread_locals.ip = ip

        response = self.get_response(request)
        
        # تنظيف السجلات الأقدم من سنة تلقائياً (بنسبة 1% من الطلبات لتخفيف الضغط وتقليل استخدام الموارد)
        if random.randint(1, 100) == 1:
            threading.Thread(target=cleanup_old_audit_logs, daemon=True).start()
            
        # تنظيف البيانات بعد انتهاء الريكويست لمنع التداخل بين الطلبات
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user
        if hasattr(_thread_locals, 'ip'):
            del _thread_locals.ip
            
        return response

class BranchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.branch = None
        request.user_allowed_branches = None
        
        try:
            from django.db import connection
            if connection.schema_name == 'public':
                return self.get_response(request)
        except Exception:
            pass
            
        if request.user.is_authenticated:
            try:
                from erp.models import Branch
                if request.user.is_superuser:
                    request.user_allowed_branches = Branch.objects.filter(is_active=True)
                elif hasattr(request.user, 'employee_profile'):
                    request.user_allowed_branches = request.user.employee_profile.allowed_branches.filter(is_active=True)
                else:
                    request.user_allowed_branches = Branch.objects.none()

                # Try getting branch from session first
                branch_id = request.session.get('active_branch_id')
                
                if branch_id == 'all':
                    request.branch = None
                elif branch_id:
                    request.branch = Branch.objects.filter(id=branch_id, is_active=True).first()
                
                if not branch_id:
                    # Fallback to employee profile active_branch or first allowed branch
                    if hasattr(request.user, 'employee_profile'):
                        profile = request.user.employee_profile
                        request.branch = profile.active_branch
                        
                        if not request.branch:
                            request.branch = profile.allowed_branches.filter(is_active=True).first()
                            if request.branch:
                                profile.active_branch = request.branch
                                profile.save(update_fields=['active_branch'])
                                
                    # If still no branch, fallback to the first active branch globally
                    if not request.branch:
                        request.branch = Branch.objects.filter(is_active=True).first()
                        
            except Exception:
                pass
                
        response = self.get_response(request)
        return response
