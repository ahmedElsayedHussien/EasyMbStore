from django.urls import path
from erp import views
from django.contrib.auth import views as auth_views

app_name = 'erp'

urlpatterns = [
    # الدخول والخروج
    path('accounts/login/', auth_views.LoginView.as_view(template_name='erp/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='erp:login'), name='logout'),
    
    # لوحة التحكم
    path('', views.dashboard_view, name='dashboard'),
    
    # نقطة البيع (POS)
    path('pos/', views.pos_view, name='pos'),
    path('pos/search/', views.pos_product_search, name='pos_product_search'),
    path('pos/grid/', views.pos_product_grid, name='pos_product_grid'),
    path('pos/checkout/', views.pos_checkout, name='pos_checkout'),
    path('pos/inventory-snapshot/', views.pos_inventory_snapshot, name='pos_inventory_snapshot'),
    path('sales/<int:pk>/', views.sale_invoice_detail, name='sale_detail'),
    
    # شراء المستعمل
    path('used-purchase/', views.used_device_purchase, name='used_purchase'),
    path('devices/<int:pk>/history/', views.device_history, name='device_history'),
    path('products/quick-add/', views.quick_add_product, name='quick_add_product'),
    path('products/search/', views.product_name_search, name='product_name_search'),
    
    # المشتريات
    path('purchases/', views.purchase_invoice_list, name='purchase_list'),
    path('purchases/create/', views.purchase_invoice_create, name='purchase_create'),
    path('purchases/<int:pk>/', views.purchase_invoice_detail, name='purchase_detail'),
    path('purchases/<int:pk>/pay/', views.purchase_invoice_pay, name='purchase_pay'),
    
    # حركات تحويل المخازن
    path('transfers/', views.transfer_list, name='transfer_list'),
    path('transfers/create/', views.transfer_create, name='transfer_create'),
    path('transfers/<int:pk>/complete/', views.transfer_complete, name='transfer_complete'),
    
    # الصيانة والتصليح
    path('repairs/', views.repair_ticket_list, name='repair_list'),
    path('repairs/create/', views.repair_ticket_create, name='repair_create'),
    path('repairs/<int:pk>/detail/', views.repair_ticket_detail, name='repair_detail'),
    path('repairs/<int:pk>/add-part/', views.repair_add_part, name='repair_add_part'),
    path('repairs/<int:pk>/change-status/', views.repair_change_status, name='repair_change_status'),
    path('repairs/<int:pk>/edit/', views.repair_ticket_edit, name='repair_edit'),
    path('contacts/add-ajax/', views.ajax_create_customer, name='ajax_create_customer'),
    
    # الورديات والخزينة
    path('shifts/', views.shift_manage_view, name='shift_manage'),
    path('shifts/add-expense/', views.shift_add_expense, name='shift_add_expense'),
    path('shifts/close/', views.shift_close, name='shift_close'),
    
    # الإعدادات والتهيئة
    path('setup/', views.setup_dashboard_view, name='setup_dashboard'),
    
    # المخزون والمخازن
    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    
    # التقارير الشاملة
    path('reports/', views.reports_dashboard, name='reports_dashboard'),

    # الإشعارات والواتساب
    path('notifications/', views.notifications_dashboard, name='notifications_dashboard'),
    path('notifications/settings/', views.notification_settings, name='notification_settings'),
    path('notifications/<int:log_id>/retry/', views.retry_notification, name='retry_notification'),
]
