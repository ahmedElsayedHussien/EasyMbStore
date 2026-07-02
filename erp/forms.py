from django import forms
from django.forms import inlineformset_factory
from erp.models import (
    Contact, Device, DeviceAttachment, PurchaseInvoice, PurchaseItem,
    StockTransfer, StockTransferItem, RepairTicket, RepairPartUsed, CashShift, Expense,
    Product, Warehouse, Treasury, ContactTransaction
)

# ==========================================
# 1. إعدادات المحل (Settings)
# ==========================================
class StoreSettingForm(forms.ModelForm):
    class Meta:
        from erp.models import StoreSetting
        model = StoreSetting
        fields = ['store_name', 'logo', 'receipt_header', 'receipt_footer', 'whatsapp_api_key', 'sms_api_key', 'loyalty_points_per_egp', 'egp_per_100_points']
        widgets = {
            'store_name': forms.TextInput(attrs={'class': 'form-control'}),
            'receipt_header': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'receipt_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'whatsapp_api_key': forms.TextInput(attrs={'class': 'form-control'}),
            'sms_api_key': forms.TextInput(attrs={'class': 'form-control'}),
            'loyalty_points_per_egp': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'egp_per_100_points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class BranchForm(forms.ModelForm):
    class Meta:
        from erp.models import Branch
        model = Branch
        fields = ['name', 'address', 'phone', 'latitude', 'longitude', 'allowed_radius', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'allowed_radius': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# ==========================================
# جهات الاتصال (Contacts)
# ==========================================
class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'phone', 'national_id', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم بالكامل'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الرقم القومي (14 رقم للمستعمل)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'العنوان بالكامل'}),
        }

# ==========================================
# 2. شراء الأجهزة المستعملة ومرفقاتها (Used Device & Attachments)
# ==========================================
class UsedDeviceForm(forms.ModelForm):
    treasury = forms.ModelChoiceField(queryset=Treasury.objects.filter(is_active=True), label='الخزينة (لسداد التكلفة)', required=True, widget=forms.Select(attrs={'class': 'form-select'}))
    
    class Meta:
        model = Device
        fields = ['product', 'imei', 'imei2', 'warehouse', 'cost', 'storage', 'ram', 'used_status', 'has_box', 'has_charger', 'is_tax_paid', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'imei': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'السيريال الأول / IMEI 1'}),
            'imei2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'السيريال الثاني / IMEI 2 (اختياري)'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'تكلفة الشراء (قيمة الاستبدال)'}),
            'storage': forms.Select(attrs={'class': 'form-select'}),
            'ram': forms.Select(attrs={'class': 'form-select'}),
            'used_status': forms.Select(attrs={'class': 'form-select'}),
            'has_box': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_charger': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_tax_paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'أدخل أي ملاحظات إضافية عن حالة الجهاز...'}),
        }

class DeviceAttachmentForm(forms.ModelForm):
    class Meta:
        model = DeviceAttachment
        fields = ['attachment_type', 'image', 'notes']
        widgets = {
            'attachment_type': forms.Select(attrs={'class': 'form-select'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ملاحظات إضافية'}),
        }

DeviceAttachmentFormSet = inlineformset_factory(
    Device, DeviceAttachment,
    form=DeviceAttachmentForm,
    extra=3,
    can_delete=True
)

# ==========================================
# 3. المشتريات (Purchase Invoice & Items)
# ==========================================
class PurchaseInvoiceForm(forms.ModelForm):
    class Meta:
        model = PurchaseInvoice
        fields = ['supplier', 'supplier_invoice_number', 'treasury', 'total_amount', 'discount', 'deduction_addition_tax', 'net_amount', 'payment_method', 'paid_amount']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'supplier_invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم فاتورة المورد'}),
            'treasury': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_total_amount', 'readonly': 'readonly'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_discount', 'value': '0.00'}),
            'deduction_addition_tax': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_deduction_addition_tax', 'value': '0.00'}),
            'net_amount': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_net_amount', 'readonly': 'readonly'}),
            'payment_method': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
            'paid_amount': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_paid_amount', 'value': '0.00'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['treasury'].queryset = Treasury.objects.filter(is_active=True)

class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['product', 'warehouse', 'quantity', 'unit_cost', 'imei_list', 'storage', 'ram', 'is_tax_paid']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select row-product'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control row-qty', 'min': 1}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control row-cost', 'step': '0.01'}),
            'imei_list': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'سيريالات مفصولة بفاصلة'}),
            'storage': forms.Select(attrs={'class': 'form-select row-storage'}),
            'ram': forms.Select(attrs={'class': 'form-select row-ram'}),
            'is_tax_paid': forms.CheckboxInput(attrs={'class': 'form-check-input row-tax'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        imei_list = cleaned_data.get('imei_list')
        
        if product and product.requires_imei:
            if not imei_list:
                raise forms.ValidationError(f"المنتج المختار ({product.name}) يتطلب إدخال سيريالات (IMEI).")
            # حساب عدد السيريالات
            imeis = [i.strip() for i in imei_list.split(',') if i.strip()]
            if len(imeis) != quantity:
                raise forms.ValidationError(
                    f"عدد السيريالات المدخلة ({len(imeis)}) لا يتطابق مع الكمية المحددة ({quantity}) للمنتج ({product.name})."
                )
        return cleaned_data

PurchaseItemFormSet = inlineformset_factory(
    PurchaseInvoice, PurchaseItem,
    form=PurchaseItemForm,
    extra=1,
    can_delete=True
)

# ==========================================
# 4. تحويل المخزون (Stock Transfer)
# ==========================================
class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['from_warehouse', 'to_warehouse', 'status']
        widgets = {
            'from_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class StockTransferItemForm(forms.ModelForm):
    class Meta:
        model = StockTransferItem
        fields = ['product', 'device', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'device': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

StockTransferItemFormSet = inlineformset_factory(
    StockTransfer, StockTransferItem,
    form=StockTransferItemForm,
    extra=1,
    can_delete=True
)

# ==========================================
# 5. الصيانة والتصليح (Repair Tickets)
# ==========================================
class RepairTicketForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Contact.objects.filter(
            contact_type__in=['customer', 'used_seller']
        ).order_by('name')

    class Meta:
        model = RepairTicket
        fields = ['customer', 'technician', 'device_model', 'device_imei', 'issue_description', 'status', 'labor_cost', 'warranty_days', 'parent_ticket']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'technician': forms.Select(attrs={'class': 'form-select'}),
            'device_model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: iPhone 15 Pro Max'}),
            'device_imei': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'السيريال / IMEI'}),
            'issue_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'تفاصيل المشكلة والعطل'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'labor_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'warranty_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'parent_ticket': forms.HiddenInput(),
        }

class RepairPartUsedForm(forms.ModelForm):
    class Meta:
        model = RepairPartUsed
        fields = ['product', 'warehouse', 'quantity', 'price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

RepairPartUsedFormSet = inlineformset_factory(
    RepairTicket, RepairPartUsed,
    form=RepairPartUsedForm,
    extra=1,
    can_delete=True
)

# ==========================================
# 6. الخزينة والورديات والمصروفات (Shifts & Expenses)
# ==========================================
class CashShiftOpenForm(forms.ModelForm):
    class Meta:
        model = CashShift
        fields = ['treasury', 'opening_balance']
        widgets = {
            'treasury': forms.Select(attrs={'class': 'form-select'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'أدخل مبلغ عهدة البداية'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['treasury'].required = True
        if user:
            if user.is_superuser or user.groups.filter(name='المدير العام').exists():
                self.fields['treasury'].queryset = Treasury.objects.filter(is_active=True)
            else:
                qs = Treasury.objects.filter(user=user, is_active=True)
                self.fields['treasury'].queryset = qs
                if qs.count() == 1:
                    self.fields['treasury'].initial = qs.first()

class CashShiftCloseForm(forms.ModelForm):
    class Meta:
        model = CashShift
        fields = ['actual_cash']
        widgets = {
            'actual_cash': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'أدخل المبلغ الفعلي بالدرج'}),
        }

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['treasury', 'category', 'amount', 'description']
        widgets = {
            'treasury': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'المبلغ'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الوصف / ملاحظات'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            if user.is_superuser or user.groups.filter(name='المدير العام').exists():
                self.fields['treasury'].queryset = Treasury.objects.filter(is_active=True)
            else:
                qs = Treasury.objects.filter(user=user, is_active=True)
                self.fields['treasury'].queryset = qs
                if qs.count() == 1:
                    self.fields['treasury'].initial = qs.first()



# ==========================================
# 7. إعداد وتهيئة النظام (System Configuration Forms)
# ==========================================
class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المخزن'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'cursor: pointer;'}),
        }

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'phone', 'address', 'opening_balance']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المورد / الشركة'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'العنوان بالكامل'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'رصيد أول المدة'}),
        }

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'phone', 'address', 'opening_balance']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم العميل'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'العنوان بالكامل'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'رصيد أول المدة'}),
        }

class TreasuryForm(forms.ModelForm):
    class Meta:
        model = Treasury
        fields = ['name', 'opening_balance', 'user', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الخزينة'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'الرصيد المبدئي'}),
            'user': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'cursor: pointer;'}),
        }

class ContactTransactionForm(forms.ModelForm):
    class Meta:
        model = ContactTransaction
        fields = ['contact', 'treasury', 'transaction_type', 'amount', 'description']
        widgets = {
            'contact': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'treasury': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'المبلغ'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'وصف الدفعة / ملاحظات'}),
        }

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'barcode_qr', 'product_type', 'selling_price', 'requires_imei']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الصنف'}),
            'barcode_qr': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الباركود / QR Code'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'سعر البيع'}),
            'requires_imei': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'cursor: pointer;'}),
        }


# ==========================================
# 8. نموذج إضافة مستخدم جديد للنظام (System User Form)
# ==========================================
class SystemUserCreationForm(forms.Form):
    ROLE_CHOICES = [
        ('المدير العام', 'المدير العام (General Manager)'),
        ('الكاشير والمبيعات', 'الكاشير والمبيعات (Cashier)'),
        ('فني الصيانة', 'فني الصيانة (Technician)'),
        ('أمين المخزن', 'أمين المخزن (Inventory Manager)'),
    ]
    
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستخدم (أحرف إنجليزية وأرقام)'})
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'})
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأخير'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'البريد الإلكتروني (اختياري)'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'كلمة المرور'})
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        from django.contrib.auth.models import User
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("خطأ: اسم المستخدم هذا مسجل بالفعل.")
        return username

# ==========================================
# 10. شؤون الموظفين (HR)
# ==========================================
class EmployeeProfileForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'اتركه فارغاً إذا لم ترغب بتغيير كلمة المرور'}),
        label="تغيير كلمة المرور (اختياري)",
        help_text="إذا قمت بإدخال كلمة مرور هنا، سيتم تغيير كلمة مرور حساب هذا الموظف."
    )

    class Meta:
        from erp.models import EmployeeProfile
        model = EmployeeProfile
        fields = ['user', 'new_password', 'hourly_rate', 'daily_working_hours', 'shift_start_time', 'shift_end_time', 'deduction_per_hour', 'overtime_per_hour', 'base_salary', 'is_active']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-select'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'daily_working_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'shift_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'shift_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'deduction_per_hour': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'overtime_per_hour': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'base_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_password = self.cleaned_data.get('new_password')
        
        if new_password and instance.user:
            instance.user.set_password(new_password)
            instance.user.save()
            
        if commit:
            instance.save()
        return instance


from .models import CommissionRule, SalesTarget

from .models import CommissionRule, SalesTarget

class CommissionRuleForm(forms.ModelForm):
    class Meta:
        model = CommissionRule
        fields = ['product_type', 'sales_milestone', 'commission_amount']
        widgets = {
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'sales_milestone': forms.NumberInput(attrs={'class': 'form-control'}),
            'commission_amount': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class SalesTargetForm(forms.ModelForm):
    class Meta:
        model = SalesTarget
        fields = ['user', 'period', 'target_amount', 'date']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-select'}),
            'period': forms.Select(attrs={'class': 'form-select'}),
            'target_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
