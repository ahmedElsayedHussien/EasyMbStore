import os

filepath = 'erp/views.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. purchase_checkout
content = content.replace(
    '                        treasury.balance -= invoice.paid_amount\n                        treasury.save()',
    '                        treasury.record_transaction(invoice.paid_amount, \'out\', f\'سداد فاتورة مشتريات رقم {invoice.id}\', request.user)'
)

# 2. purchase_payment
content = content.replace(
    '                treasury.balance -= amount\n                treasury.save()',
    '                treasury.record_transaction(amount, \'out\', f\'دفعة لمورد: {invoice.supplier.name} للفاتورة {invoice.id}\', request.user)'
)

# 3. repair_status_update
content = content.replace(
    '                    treasury.balance += total_cost\n                    treasury.save()',
    '                    treasury.record_transaction(total_cost, \'in\', f\'تحصيل تكلفة صيانة لتذكرة رقم #{ticket.id}\', request.user)'
)

# 4. shift_close
content = content.replace(
    '                treasury.balance += (shift.actual_cash - shift.opening_balance)\n                treasury.save()',
    '                treasury.record_transaction((shift.actual_cash - shift.opening_balance), \'in\', f\'فائض وردية: {shift.cashier.username}\', request.user)'
)

# 5. debts_list (distributed amount)
content = content.replace(
    '''                    if trans.transaction_type == 'receipt':
                        treasury.balance += distributed_amount
                    elif trans.transaction_type == 'payment':
                        treasury.balance -= distributed_amount
                    treasury.save()''',
    '''                    if trans.transaction_type == 'receipt':
                        treasury.record_transaction(distributed_amount, 'in', f"سداد ديون لـ {trans.contact.name}", request.user)
                    elif trans.transaction_type == 'payment':
                        treasury.record_transaction(distributed_amount, 'out', f"سداد ديون لـ {trans.contact.name}", request.user)'''
)

# 6. pos_checkout
content = content.replace(
    '            treasury.balance += amount\n            treasury.save()',
    '            treasury.record_transaction(amount, \'in\', f\'فاتورة مبيعات POS رقم {invoice.id}\', request.user)'
)

# 7. payroll_add
content = content.replace(
    '            treasury.balance -= payroll.net_salary\n            treasury.save()',
    '            treasury.record_transaction(payroll.net_salary, \'out\', f\'صرف راتب الموظف {payroll.employee.user.username}\', request.user)'
)

# 8. sale_return_checkout
content = content.replace(
    '                    treasury.balance -= refund_amount\n                    treasury.save()',
    '                    treasury.record_transaction(refund_amount, \'out\', f\'مرتجع مبيعات للفاتورة الأصلية {original_invoice.id}\', request.user)'
)

# 9. purchase_return_checkout
content = content.replace(
    '                    treasury.balance += refund_amount\n                    treasury.save()',
    '                    treasury.record_transaction(refund_amount, \'in\', f\'مرتجع مشتريات للفاتورة الأصلية {original_invoice.id}\', request.user)'
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done replacements')
