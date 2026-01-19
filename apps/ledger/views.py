from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from apps.common.views.base import ApiView
from .models import Voucher, Account, AccountGroup, FinancialYear, JournalEntry, VoucherType
from core.models import Business
from .services.ledger_service import LedgerService
from decimal import Decimal
from django.db import models
from django.db.models import Sum, Q
from django.contrib import messages
import json
from .services.automation_service import AutomationService

@login_required
@require_POST
def reconcile_ledgers(request, biz_pk):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    matches_found = AutomationService.reconcile_pending_payments(business)
    
    if matches_found > 0:
        messages.success(request, f"God-Level Reconciliation Complete: {matches_found} payments matched to actual invoices!")
    else:
        messages.info(request, "Reconciliation Engine finished: No new matches found currently.")
        
    return redirect('ledger:trial-balance', biz_pk=biz_pk)

@login_required
def day_book_view(request, biz_pk):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # Chronological is usually ascending for a Day Book
    vouchers = Voucher.objects.filter(business=business).order_by('date', 'created_at').prefetch_related('entries__account')
    
    # Calculate totals
    total_dr = JournalEntry.objects.filter(voucher__business=business).aggregate(Sum('debit'))['debit__sum'] or 0
    total_cr = JournalEntry.objects.filter(voucher__business=business).aggregate(Sum('credit'))['credit__sum'] or 0
    
    return render(request, 'ledger/daybook.html', {
        'business': business, 
        'vouchers': vouchers,
        'total_dr': total_dr,
        'total_cr': total_cr
    })

@login_required
def trial_balance_view(request, biz_pk):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # Elite CFO Strategy: Use aggregation for massive performance gains
    # Calculate all balances in a single pass
    balances = JournalEntry.objects.filter(
        voucher__business=business, 
        voucher__is_draft=False
    ).values('account_id').annotate(
        dr_total=Sum('debit'),
        cr_total=Sum('credit')
    )
    
    # Map for easy lookup
    bal_map = {b['account_id']: (b['dr_total'] or Decimal('0')) - (b['cr_total'] or Decimal('0')) for b in balances}
    
    accounts = Account.objects.filter(business=business).select_related('group')
    
    report_data = []
    total_dr = Decimal('0.00')
    total_cr = Decimal('0.00')
    
    for acc in accounts:
        # Get balance from map or use 0
        movement = bal_map.get(acc.id, Decimal('0'))
        bal = acc.opening_balance + movement
        
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
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # Professional Aggregation: Single pass for all P&L movements
    pnl_vouchers = [VoucherType.SALES, VoucherType.PURCHASE, VoucherType.JOURNAL, VoucherType.CREDIT_NOTE, VoucherType.DEBIT_NOTE]
    
    balances = JournalEntry.objects.filter(
        voucher__business=business,
        voucher__voucher_type__in=pnl_vouchers,
        voucher__is_draft=False,
        account__group__classification__in=['INCOME', 'EXPENSE']
    ).values('account_id').annotate(dr=Sum('debit'), cr=Sum('credit'))
    
    bal_map = {b['account_id']: (b['dr'] or Decimal('0')) - (b['cr'] or Decimal('0')) for b in balances}

    # 1. Income
    income_accounts = Account.objects.filter(business=business, group__classification='INCOME')
    income_data = []
    total_income = Decimal('0')
    for acc in income_accounts:
        bal = -bal_map.get(acc.id, Decimal('0'))
        if bal != 0:
            income_data.append({'name': acc.name, 'amount': bal})
            total_income += bal
            
    # 2. Expenses
    expense_accounts = Account.objects.filter(business=business, group__classification='EXPENSE')
    expense_data = []
    total_expense = Decimal('0')
    for acc in expense_accounts:
        bal = bal_map.get(acc.id, Decimal('0'))
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
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    # 1. Assets
    asset_accounts = Account.objects.filter(business=business, group__classification='ASSET')
    asset_balances = JournalEntry.objects.filter(
        account__in=asset_accounts, voucher__is_draft=False
    ).values('account_id').annotate(dr=Sum('debit'), cr=Sum('credit'))
    
    asset_map = {b['account_id']: (b['dr'] or Decimal('0')) - (b['cr'] or Decimal('0')) for b in asset_balances}
    assets = []
    total_assets = Decimal('0.00')
    for acc in asset_accounts:
        bal = acc.opening_balance + asset_map.get(acc.id, Decimal('0'))
        if bal != 0:
            assets.append({'name': acc.name, 'amount': bal})
            total_assets += bal
            
    # 2. Liabilities & Equity
    liab_accounts = Account.objects.filter(business=business, group__classification__in=['LIABILITY', 'EQUITY'])
    liab_balances = JournalEntry.objects.filter(
        account__in=liab_accounts, voucher__is_draft=False
    ).values('account_id').annotate(dr=Sum('debit'), cr=Sum('credit'))
    
    liab_map = {b['account_id']: (b['dr'] or Decimal('0')) - (b['cr'] or Decimal('0')) for b in liab_balances}
    liabilities = []
    total_liabilities = Decimal('0.00')
    for acc in liab_accounts:
        # Liabilities are usually Credit balances (negative in our Dr-Cr math)
        bal = - (acc.opening_balance + liab_map.get(acc.id, Decimal('0')))
        if bal != 0:
            liabilities.append({'name': acc.name, 'amount': bal})
            total_liabilities += bal
            
    # 3. Incorporate Net Profit/Loss (Elite CFO Standard)
    pnl = JournalEntry.objects.filter(
        account__business=business, 
        account__group__classification__in=['INCOME', 'EXPENSE'], 
        voucher__is_draft=False
    ).aggregate(
        inc=Sum('credit', filter=models.Q(account__group__classification='INCOME')) - Sum('debit', filter=models.Q(account__group__classification='INCOME')),
        exp=Sum('debit', filter=models.Q(account__group__classification='EXPENSE')) - Sum('credit', filter=models.Q(account__group__classification='EXPENSE'))
    )
    
    net_profit = (pnl['inc'] or Decimal('0')) - (pnl['exp'] or Decimal('0'))
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
        doc_id = request.GET.get('document_id')
        business = request.business
        
        if not business and doc_id:
            # Try to infer business from document if middleware missed it
            from core.models import Document
            doc = get_object_or_404(Document, id=doc_id, business__created_by=request.user)
            business = doc.business

        if not business:
            return self.error_response("Business context required", status=400)
            
        from .services.tally_service import TallyExportService
        from django.http import HttpResponse
        
        xml_data = TallyExportService.export_business_vouchers(business, document_id=doc_id)
        
        filename = f"tally_import_{business.id}.xml"
        if doc_id: filename = f"tally_doc_{doc_id}.xml"

        response = HttpResponse(xml_data, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

@login_required
@require_POST
def reclassify_entry(request):
    entry_id = request.POST.get('entry_id')
    new_account_id = request.POST.get('account_id')
    
    if request.user.is_superuser:
        entry = get_object_or_404(JournalEntry, id=entry_id)
    else:
        entry = get_object_or_404(JournalEntry, id=entry_id, voucher__business__created_by=request.user)
        
    new_acc = get_object_or_404(Account, id=new_account_id, business=entry.voucher.business)
    
    entry.account = new_acc
    entry.save()
    
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
@require_POST
def create_account_and_reclassify(request):
    """
    Expert Mode: Create a new ledger on the fly and map the entry to it.
    """
    entry_id = request.POST.get('entry_id')
    account_name = request.POST.get('name')
    group_id = request.POST.get('group_id')

    if request.user.is_superuser:
        entry = get_object_or_404(JournalEntry, id=entry_id)
    else:
        entry = get_object_or_404(JournalEntry, id=entry_id, voucher__business__created_by=request.user)

    business = entry.voucher.business
    group = get_object_or_404(AccountGroup, id=group_id, business=business)

    # Create the new account
    new_acc = Account.objects.create(
        business=business,
        group=group,
        name=account_name,
        classification=group.classification
    )

    # Reclassify the entry
    entry.account = new_acc
    entry.save()

    messages.success(request, f"Created new ledger '{account_name}' and reclassified entry.")
    return redirect(request.META.get('HTTP_REFERER', '/'))
@login_required
@require_POST
def record_capital_infusion(request, biz_pk):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=biz_pk)
    else:
        business = get_object_or_404(Business, pk=biz_pk, created_by=request.user)
    
    amount_str = request.POST.get('amount', '0')
    try:
        amount = Decimal(amount_str)
    except:
        messages.error(request, "Invalid amount.")
        return redirect('ledger:trial-balance', biz_pk=biz_pk)

    if amount <= 0:
        messages.error(request, "Amount must be positive.")
        return redirect('ledger:trial-balance', biz_pk=biz_pk)

    # 1. Identify/Create Ledgers
    from .services.automation_service import AutomationService
    bank_acc = AutomationService.get_or_create_default_account(business, "Main Bank Account", "Bank Accounts")
    capital_acc = AutomationService.get_or_create_default_account(business, "Owner's Capital", "Capital Account")

    # 2. Setup Voucher
    from datetime import date
    fy = LedgerService.initialize_financial_year(business)

    voucher_data = {
        'voucher_type': VoucherType.RECEIPT,
        'date': date.today(),
        'fy_id': fy.id,
        'narration': f"Opening Capital Infusion / Initial Fund | Reference: QuickSetup",
        'is_draft': False # Posting directly to fix trial balance
    }

    entries_data = [
        {'account_id': bank_acc.id, 'debit': amount, 'credit': 0},
        {'account_id': capital_acc.id, 'debit': 0, 'credit': amount}
    ]

    try:
        vch = LedgerService.create_voucher(business, voucher_data, entries_data)
        messages.success(request, f"Successfully recorded ₹{amount} infusion. Negative equity warnings resolved!")
    except Exception as e:
        messages.error(request, f"Failed to record infusion: {e}")

    return redirect('ledger:trial-balance', biz_pk=biz_pk)
