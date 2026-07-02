from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db.models import Q

def is_admin(user):
    return user.is_superuser or user.groups.filter(name='المدير العام').exists()

@login_required
@user_passes_test(is_admin)
def manage_users(request):
    # لا يمكن للمستخدمين إضافة مستخدم جديد من هنا. (فقط عبر الإدارة المركزية)
    if request.method == 'POST':
        messages.error(request, 'لا يمكن إضافة مستخدمين من الواجهة. يرجى التواصل مع الإدارة المركزية.')
        return redirect('erp:manage_users')

    search_query = request.GET.get('q', '')
    if search_query:
        users = User.objects.filter(Q(username__icontains=search_query) | Q(email__icontains=search_query)).order_by('-date_joined')
    else:
        users = User.objects.all().order_by('-date_joined')
        
    groups = Group.objects.all()
    from erp.models import Branch
    branches = Branch.objects.all()
    
    context = {
        'users': users,
        'groups': groups,
        'branches': branches,
    }
    return render(request, 'erp/users_management.html', context)

@login_required
@user_passes_test(is_admin)
def toggle_user_status(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        if user == request.user:
            messages.error(request, 'لا يمكنك إيقاف حسابك الشخصي.')
        elif user.is_superuser and not request.user.is_superuser:
            messages.error(request, 'لا تملك صلاحية لتعديل حساب مدير عام.')
        else:
            user.is_active = not user.is_active
            user.save()
            status_text = "تفعيل" if user.is_active else "إيقاف"
            messages.success(request, f'تم {status_text} حساب {user.username} بنجاح.')
    return redirect('erp:manage_users')

@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        if user == request.user:
            messages.error(request, 'لا يمكنك حذف حسابك الشخصي.')
        elif user.is_superuser:
            messages.error(request, 'لا يمكنك حذف حساب مدير عام.')
        else:
            username = user.username
            user.delete()
            messages.success(request, f'تم حذف المستخدم {username} بنجاح.')
    return redirect('erp:manage_users')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        if user.is_superuser:
            messages.error(request, 'لا يمكنك تعديل صلاحيات مدير عام.')
            return redirect('erp:manage_users')
            
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        group_id = request.POST.get('group')
        
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        
        user.groups.clear()
        if group_id:
            try:
                group = Group.objects.get(id=group_id)
                user.groups.add(group)
            except Group.DoesNotExist:
                pass
                
        active_branch_id = request.POST.get('active_branch')
        from erp.models import EmployeeProfile, Branch
        profile, created = EmployeeProfile.objects.get_or_create(user=user)
        if active_branch_id:
            try:
                branch = Branch.objects.get(id=active_branch_id)
                profile.active_branch = branch
                profile.allowed_branches.add(branch)
            except Branch.DoesNotExist:
                pass
        else:
            profile.active_branch = None
            
        profile.save()
                
        messages.success(request, f'تم تحديث بيانات المستخدم {user.username} بنجاح.')
        
    return redirect('erp:manage_users')


from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

@login_required
@user_passes_test(is_admin)
def manage_roles(request):
    if request.method == 'POST':
        role_name = request.POST.get('role_name')
        if role_name:
            if Group.objects.filter(name=role_name).exists():
                messages.error(request, 'اسم الصلاحية موجود بالفعل.')
            else:
                Group.objects.create(name=role_name)
                messages.success(request, f'تم إنشاء الصلاحية {role_name} بنجاح.')
        return redirect('erp:manage_roles')

    roles = Group.objects.all().order_by('id')
    return render(request, 'erp/roles_management.html', {'roles': roles})

@login_required
@user_passes_test(is_admin)
def edit_role(request, role_id):
    role = get_object_or_404(Group, id=role_id)
    
    if request.method == 'POST':
        # Get list of permission IDs from the form
        perm_ids = request.POST.getlist('permissions')
        role.permissions.set(perm_ids)
        messages.success(request, 'تم تحديث الصلاحيات بنجاح.')
        return redirect('erp:manage_roles')

    # Get all permissions related to our ERP app
    erp_content_types = ContentType.objects.filter(app_label='erp')
    permissions = Permission.objects.filter(content_type__in=erp_content_types).select_related('content_type')
    
    # Group permissions by content type for easier display
    perms_by_model = {}
    for p in permissions:
        model_name = p.content_type.model
        if model_name not in perms_by_model:
            perms_by_model[model_name] = []
        perms_by_model[model_name].append(p)
        
    role_perms = role.permissions.values_list('id', flat=True)
    
    context = {
        'role': role,
        'perms_by_model': perms_by_model,
        'role_perms': list(role_perms)
    }
    return render(request, 'erp/role_edit.html', context)

@login_required
@user_passes_test(is_admin)
def delete_role(request, role_id):
    if request.method == 'POST':
        role = get_object_or_404(Group, id=role_id)
        if role.user_set.exists():
            messages.error(request, 'لا يمكن حذف هذه الصلاحية لارتباط مستخدمين بها. قم بنقل المستخدمين أولاً.')
        else:
            name = role.name
            role.delete()
            messages.success(request, f'تم حذف الصلاحية {name} بنجاح.')
    return redirect('erp:manage_roles')
