path = 'erp/models.py'
with open(path, 'r', encoding='windows-1256') as f:
    lines = f.readlines()

found_idx = -1
for idx, line in enumerate(lines):
    if 'class PurchaseItem(models.Model):' in line:
        found_idx = idx
        break

if found_idx != -1:
    print(f"Found class PurchaseItem at line {found_idx+1}")
    # Find imei_list line inside this class
    imei_idx = -1
    for idx in range(found_idx + 1, len(lines)):
        # If we hit another class, stop
        if lines[idx].startswith('class '):
            break
        if 'imei_list' in lines[idx]:
            imei_idx = idx
            break
            
    if imei_idx != -1:
        print(f"Found imei_list at line {imei_idx+1}")
        # Insert fields after imei_idx line
        fields = [
            "    \n",
            "    # المواصفات الإضافية للأجهزة الموردة\n",
            '    storage = models.CharField(max_length=20, choices=Device.STORAGE_CHOICES, blank=True, null=True, verbose_name="المساحة")\n',
            '    ram = models.CharField(max_length=20, choices=Device.RAM_CHOICES, blank=True, null=True, verbose_name="الرام")\n',
            '    is_tax_paid = models.BooleanField(default=False, verbose_name="خالص الضريبة")\n'
        ]
        
        # Check if already added
        already_added = False
        for idx in range(imei_idx + 1, min(imei_idx + 10, len(lines))):
            if 'storage = models.CharField' in lines[idx]:
                already_added = True
                break
                
        if not already_added:
            lines[imei_idx+1:imei_idx+1] = fields
            with open(path, 'w', encoding='windows-1256') as f:
                f.writelines(lines)
            print("REPLACEMENT SUCCESSFUL")
        else:
            print("FIELDS ALREADY ADDED")
    else:
        print("ERROR: imei_list line not found")
else:
    print("ERROR: class PurchaseItem not found")
