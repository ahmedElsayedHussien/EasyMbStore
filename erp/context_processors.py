def branch_processor(request):
    """
    يضيف متغير `active_branch` والمتغير `user_allowed_branches` 
    لكل القوالب (Templates) للتمكن من عرض اسم الفرع والتبديل بينهم.
    """
    context = {}
    if hasattr(request, 'branch'):
        context['active_branch'] = request.branch
        context['is_all_branches'] = (request.branch is None and request.session.get('active_branch_id') == 'all')
        
    if hasattr(request, 'user_allowed_branches') and request.user_allowed_branches:
        context['user_allowed_branches'] = request.user_allowed_branches
            
    return context
