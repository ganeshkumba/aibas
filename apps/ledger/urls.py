from django.urls import path

from . import views

app_name = 'ledger'

urlpatterns = [
    path('vouchers/', views.VoucherListView.as_view(), name='voucher-list'),
    path('vouchers/create/', views.VoucherCreateView.as_view(), name='voucher-create'),
    path('accounts/', views.AccountListView.as_view(), name='account-list'),
    path('export/tally/', views.TallyExportView.as_view(), name='tally-export'),
    
    # HTML Reports
    path('reports/<int:biz_pk>/daybook/', views.day_book_view, name='day-book'),
    path('reports/<int:biz_pk>/trial-balance/', views.trial_balance_view, name='trial-balance'),
    path('reports/<int:biz_pk>/pl/', views.profit_loss_view, name='profit-loss'),
    path('reports/<int:biz_pk>/balance-sheet/', views.balance_sheet_view, name='balance-sheet'),
    path('reclassify-entry/', views.reclassify_entry, name='reclassify-entry'),
    path('create-account-reclassify/', views.create_account_and_reclassify, name='create-account-reclassify'),
    path('reports/<int:biz_pk>/capital-infusion/', views.record_capital_infusion, name='capital-infusion'),
    path('reports/<int:biz_pk>/reconcile/', views.reconcile_ledgers, name='reconcile-ledgers'),
]
