from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import inlineformset_factory
from .models import StockTransfer, StockTransferItem, Warehouse
from .middleware import get_current_branch

@login_required
def transfer_list(request):
    branch = get_current_branch(request)
    # Get warehouses for current branch
    warehouses = Warehouse.objects.filter(branch=branch)
    # Incoming transfers (where to_warehouse is in this branch)
    incoming = StockTransfer.objects.filter(to_warehouse__in=warehouses).order_by('-created_at')
    # Outgoing transfers (where from_warehouse is in this branch)
    outgoing = StockTransfer.objects.filter(from_warehouse__in=warehouses).order_by('-created_at')
    
    return render(request, 'erp/transfers/transfer_list.html', {
        'incoming': incoming,
        'outgoing': outgoing
    })

@login_required
def transfer_create(request):
    branch = get_current_branch(request)
    warehouses = Warehouse.objects.filter(branch=branch)
    all_warehouses = Warehouse.objects.filter(is_active=True)
    
    StockTransferItemFormSet = inlineformset_factory(
        StockTransfer, StockTransferItem, 
        fields=('product', 'device', 'quantity'),
        extra=1, can_delete=True
    )

    if request.method == 'POST':
        from_warehouse_id = request.POST.get('from_warehouse')
        to_warehouse_id = request.POST.get('to_warehouse')
        
        if from_warehouse_id and to_warehouse_id:
            transfer = StockTransfer(
                from_warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                created_by=request.user,
                status='pending'
            )
            formset = StockTransferItemFormSet(request.POST, instance=transfer)
            if formset.is_valid():
                transfer.save()
                formset.save()
                messages.success(request, "تم إنشاء حركة التحويل بنجاح. البضاعة الآن 'قيد النقل'.")
                return redirect('transfer_list')
    else:
        formset = StockTransferItemFormSet()

    return render(request, 'erp/transfers/transfer_form.html', {
        'warehouses': warehouses,
        'all_warehouses': all_warehouses,
        'formset': formset
    })

@login_required
def transfer_receive(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    branch = get_current_branch(request)
    
    # Check if the transfer is to a warehouse in the current branch
    if transfer.to_warehouse.branch != branch:
        messages.error(request, "لا يحق لك استلام تحويل موجه لفرع آخر.")
        return redirect('transfer_list')

    if request.method == 'POST':
        if transfer.status == 'pending':
            transfer.status = 'completed'
            transfer.save()
            messages.success(request, "تم تأكيد الاستلام بنجاح، وتحديث المخزون.")
        else:
            messages.warning(request, "هذا التحويل تم استلامه مسبقاً.")
        return redirect('transfer_list')

    return render(request, 'erp/transfers/transfer_detail.html', {
        'transfer': transfer
    })
