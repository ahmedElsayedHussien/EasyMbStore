from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.forms.models import model_to_dict
from .models import (
    AuditLog, Product, Device, PurchaseInvoice, SaleInvoice, 
    Expense, Contact, TreasuryTransaction, RepairTicket
)
from .middleware import get_current_user, get_current_ip

# Models to track
TRACKED_MODELS = [
    Product, Device, PurchaseInvoice, SaleInvoice, 
    Expense, Contact, TreasuryTransaction, RepairTicket
]

# Temporary storage for pre_save state
_unregistered_old_states = {}

def get_model_name(instance):
    return instance._meta.verbose_name

def serialize_instance(instance):
    try:
        # Get standard fields
        data = model_to_dict(instance)
        # Convert decimal/datetime to string for JSON serialization
        for key, value in data.items():
            data[key] = str(value)
        return data
    except Exception:
        return {}

@receiver(pre_save)
def capture_old_state(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            _unregistered_old_states[f"{sender.__name__}_{instance.pk}"] = serialize_instance(old_instance)
        except sender.DoesNotExist:
            pass

@receiver(post_save)
def log_create_update(sender, instance, created, **kwargs):
    if sender not in TRACKED_MODELS:
        return
        
    user = get_current_user()
    ip = get_current_ip()
    model_name = get_model_name(instance)
    obj_repr = str(instance)
    
    if created:
        AuditLog.objects.create(
            user=user,
            action='create',
            model_name=model_name,
            object_id=str(instance.pk),
            object_repr=obj_repr,
            changes={'new': serialize_instance(instance)},
            ip_address=ip
        )
    else:
        state_key = f"{sender.__name__}_{instance.pk}"
        old_state = _unregistered_old_states.pop(state_key, {})
        new_state = serialize_instance(instance)
        
        # Calculate differences
        changes = {}
        for key, new_val in new_state.items():
            old_val = old_state.get(key)
            if old_val != new_val:
                changes[key] = {'old': old_val, 'new': new_val}
                
        if changes:
            AuditLog.objects.create(
                user=user,
                action='update',
                model_name=model_name,
                object_id=str(instance.pk),
                object_repr=obj_repr,
                changes=changes,
                ip_address=ip
            )

@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
        
    user = get_current_user()
    ip = get_current_ip()
    model_name = get_model_name(instance)
    obj_repr = str(instance)
    
    AuditLog.objects.create(
        user=user,
        action='delete',
        model_name=model_name,
        object_id=str(instance.pk),
        object_repr=obj_repr,
        changes={'deleted_data': serialize_instance(instance)},
        ip_address=ip
    )

# --- Stock Transfer Automation ---
from django.core.exceptions import ValidationError
from .models import StockTransfer, Stock

@receiver(pre_save, sender=StockTransfer)
def process_stock_transfer(sender, instance, **kwargs):
    if instance.pk:
        old_instance = StockTransfer.objects.get(pk=instance.pk)
        if old_instance.status == 'pending' and instance.status == 'completed':
            # Process transfer
            for item in instance.items.all():
                if item.device:
                    item.device.warehouse = instance.to_warehouse
                    item.device.save()
                else:
                    # Deduct from source
                    source_stock, _ = Stock.objects.get_or_create(
                        product=item.product, 
                        warehouse=instance.from_warehouse
                    )
                    if source_stock.quantity < item.quantity:
                        raise ValidationError(f"لا يوجد رصيد كافٍ من {item.product.name} في المخزن المُرسل.")
                    source_stock.quantity -= item.quantity
                    source_stock.save()
                    
                    # Add to destination
                    dest_stock, _ = Stock.objects.get_or_create(
                        product=item.product, 
                        warehouse=instance.to_warehouse
                    )
                    dest_stock.quantity += item.quantity
                    dest_stock.save()
