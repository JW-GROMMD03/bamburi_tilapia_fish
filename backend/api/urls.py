from django.urls import path
from . import views, auth_views, dashboard_views
from django.http import JsonResponse

def test_view(request):
    return JsonResponse({'status': 'ok', 'message': 'Server is running!'})


urlpatterns = [
    # Auth
    path('auth/signup/', auth_views.signup, name='signup'),
    path('auth/login/', auth_views.login, name='login'),
    path('auth/profile/', auth_views.get_profile, name='profile'),
    path('auth/cashiers/', auth_views.get_cashiers, name='cashiers'),
    path('auth/managers/', auth_views.get_cashiers, name='managers'),  # uses same function
    path('auth/approve/<str:user_id>/', auth_views.approve_cashier, name='approve'),
    path('auth/block/<str:user_id>/', auth_views.block_user, name='block'),
    path('auth/reject/<str:user_id>/', auth_views.reject_user, name='reject'),
    path('auth/unblock/<str:user_id>/', auth_views.unblock_user, name='unblock'),
    path('auth/reset-password/<str:user_id>/', auth_views.reset_password, name='reset-password'),
    
    # Dashboards
    path('dashboard/admin/', dashboard_views.admin_dashboard, name='admin-dashboard'),
    path('dashboard/manager/', dashboard_views.manager_dashboard, name='manager-dashboard'),
    path('dashboard/cashier/', dashboard_views.cashier_dashboard, name='cashier-dashboard'),
    path('dashboard/monthly/', dashboard_views.monthly_comparison, name='monthly'),
    
    # Transactions
    path('transactions/', views.transactions, name='transactions'),
    path('transactions/<int:transaction_id>/', views.delete_transaction, name='delete-transaction'),
    
    # Expenses
    path('expenses/', views.expenses, name='expenses'),
    path('expenses/<int:expense_id>/', views.delete_expense, name='delete-expense'),
    
    # Credit
    path('credit/', views.credit_sales, name='credit-sales'),
    path('credit/<int:credit_id>/', views.update_credit, name='update-credit'),
    
    # Stock / Inventory
    path('stock/', views.stock_list, name='stock-list'),
    path('stock/use/', views.use_stock, name='use-stock'),
    path('stock/analysis/', views.stock_analysis, name='stock-analysis'),
    
    # Soda
    path('soda/', views.soda_stock, name='soda-stock'),
    
    # Water
    path('water/', views.water_stock, name='water-stock'),
    
    # Trash
    path('trash/', views.trash, name='trash'),
    path('trash/<int:trash_id>/', views.delete_trash_item, name='delete-trash-item'),
    path('trash/restore/<int:trash_id>/', views.restore_trash, name='restore-trash'),
    path('trash/empty/', views.empty_trash_all, name='empty-trash'),
    
   
    # Menu Items Management - FIXED (removed duplicates and old functions)
    path('items/', views.menu_items, name='menu-items'),
    path('items/<int:item_id>/', views.menu_item_detail, name='menu-item-detail'),
    path('items/<int:item_id>/toggle/', views.toggle_menu_item, name='toggle-menu-item'),
    
    # Profile Management
    path('auth/update-avatar/', views.update_avatar, name='update-avatar'),
    path('auth/update-profile/', views.update_profile, name='update-profile'),
    path('auth/change-password/', views.change_password, name='change-password'),
    path('auth/profile/', views.get_profile, name='get-profile'),


    # Audit
    path('audit-logs/', views.get_audit_logs, name='audit-logs'),
    
    # Shift Reports
    path('shift-reports/', views.shift_reports, name='shift-reports'),
    
    # Summary
    path('today-summary/', views.today_summary, name='today-summary'),
    
    
    path('test/', test_view, name='test'),
    
    path('dashboard/analytics/', views.analytics_dashboard, name='analytics-dashboard'),

    # Menu sync endpoints - FIXED (removed duplicate menu/items/)
    path('menu/version/', views.menu_version, name='menu-version'),
    path('menu/items/', views.get_menu_items, name='menu-items-sync'),
    path('menu/refresh/', views.force_menu_refresh, name='menu-refresh'),
    
    # QR Delete endpoints
path('qr/approve/', views.approve_qr_delete, name='qr-approve'),
path('qr/check/', views.check_pending_approvals, name='qr-check'),
]