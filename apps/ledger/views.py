from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from apps.common.views.base import ApiView
from .models import Voucher, Account, AccountGroup, FinancialYear
from core.models import Business
from .services.ledger_service import LedgerService
from decimal import Decimal
import json

@login_required
def day_book_view(request, biz_pk):
    business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    vouchers = Voucher.objects.filter(business=business).order_by('-date', '-created_at').prefetch_related('entries__account')
    return render(request, 'ledger/daybook.html', {'business': business, 'vouchers': vouchers})

@login_required
def trial_balance_view(request, biz_pk):
    business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    accounts = Account.objects.filter(business=business).select_related('group')
    
    report_data = []
    total_dr = Decimal('0')
    total_cr = Decimal('0')
    
    for acc in accounts:
        bal = LedgerService.get_account_balance(acc.id, business=business)
        if bal != 0:
            dr = bal if bal > 0 else 0
            cr = -bal if bal < 0 else 0
            report_data.append({
                'account': acc,
                'debit': dr,
                'credit': cr
            })
            total_dr += dr
            total_cr += cr
            
    health_checks = LedgerService.get_accounting_health_checks(business)
            
    return render(request, 'ledger/trial_balance.html', {
        'business': business, 
        'report_data': report_data,
        'total_dr': total_dr,
        'total_cr': total_cr,
        'health_checks': health_checks
    })

@login_required
def profit_loss_view(request, biz_pk):
    business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # 1. Income
    income_accounts = Account.objects.filter(business=business, group__classification='INCOME')
    income_data = []
    total_income = Decimal('0')
    for acc in income_accounts:
        bal = -LedgerService.get_pnl_balance(acc.id, business=business) # Use P&L specific balance
        if bal != 0:
            income_data.append({'name': acc.name, 'amount': bal})
            total_income += bal
            
    # 2. Expenses
    expense_accounts = Account.objects.filter(business=business, group__classification='EXPENSE')
    expense_data = []
    total_expense = Decimal('0')
    for acc in expense_accounts:
        bal = LedgerService.get_pnl_balance(acc.id, business=business) # Use P&L specific balance
        if bal != 0:
            expense_data.append({'name': acc.name, 'amount': bal})
            total_expense += bal
            
    net_profit = total_income - total_expense
    
    return render(request, 'ledger/profit_loss.html', {
        'business': business,
        'income_data': income_data,
        'expense_data': expense_data,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_profit': net_profit
    })

@login_required
def balance_sheet_view(request, biz_pk):
    business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # Assets
    asset_accounts = Account.objects.filter(business=business, group__classification='ASSET')
    assets = []
    total_assets = Decimal('0')
    for acc in asset_accounts:
        bal = LedgerService.get_account_balance(acc.id, business=business)
        if bal != 0:
            assets.append({'name': acc.name, 'amount': bal})
            total_assets += bal
            
    # Liabilities
    liab_accounts = Account.objects.filter(business=business, group__classification__in=['LIABILITY', 'EQUITY'])
    liabilities = []
    total_liabilities = Decimal('0')
    for acc in liab_accounts:
        bal = -LedgerService.get_account_balance(acc.id, business=business)
        if bal != 0:
            liabilities.append({'name': acc.name, 'amount': bal})
            total_liabilities += bal
            
    # Also include Net Profit in Liabilities (Capital) side
    # Calculate P&L for this year (simplified)
    # We should probably have a more robust way to get P&L, 
    # but for now we'll redo the calculation or use a helper.
    from core.processor import generate_business_summary
    summary = generate_business_summary(business)
    net_profit = summary['net_profit']
    total_liabilities += net_profit

    return render(request, 'ledger/balance_sheet.html', {
        'business': business,
        'assets': assets,
        'liabilities': liabilities,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'net_profit': net_profit
    })

class VoucherListView(ApiView):
    def get(self, request):
        if not request.business:
            return self.error_response("Business context required", status=400)
            
        vouchers = Voucher.objects.filter(business=request.business).prefetch_related('entries')
        
        data = []
        for v in vouchers:
            data.append({
                "id": str(v.id),
                "type": v.voucher_type,
                "number": v.voucher_number,
                "date": v.date.isoformat(),
                "narration": v.narration,
                "is_draft": v.is_draft,
                "entries": [
                    {
                        "account": e.account.name,
                        "debit": str(e.debit),
                        "credit": str(e.credit)
                    } for e in v.entries.all()
                ]
            })
            
        return self.success_response(data)

class VoucherCreateView(ApiView):
    def post(self, request):
        if not request.business:
            return self.error_response("Business context required", status=400)
            
        body = self.get_json_body()
        
        # In a real app, we'd use a Validator class here
        # For brevity, calling service directly
        try:
            voucher = LedgerService.create_voucher(
                business=request.business,
                voucher_data={
                    "date": body['date'],
                    "voucher_type": body['type'],
                    "voucher_number": body['number'],
                    "fy_id": body['fy_id'],
                    "narration": body.get('narration', ''),
                    "is_draft": body.get('is_draft', False)
                },
                entries_data=body['entries']
            )
            return self.success_response({"id": str(voucher.id), "number": voucher.voucher_number}, status=201)
        except KeyError as e:
            return self.error_response(f"Missing field: {str(e)}")

class AccountListView(ApiView):
    def get(self, request):
        if not request.business:
            return self.error_response("Business context required", status=400)
            
        accounts = Account.objects.filter(business=request.business).select_related('group')
        data = [{
            "id": str(a.id),
            "name": a.name,
            "group": a.group.name,
            "classification": a.group.classification,
            "balance": str(LedgerService.get_account_balance(a.id, business=request.business))
        } for a in accounts]
        
        return self.success_response(data)

class TallyExportView(ApiView):
    def get(self, request):
        if not request.business:
            return self.error_response("Business context required", status=400)
            
        from .services.tally_service import TallyExportService
        from django.http import HttpResponse
        
        xml_data = TallyExportService.export_business_vouchers(request.business)
        
        response = HttpResponse(xml_data, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="tally_import_{request.business.id}.xml"'
        return response
