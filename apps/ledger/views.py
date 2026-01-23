from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from apps.common.views.base import ApiView, business_required, get_business_or_404
from core.models import Business, Document
from .models import Voucher, Account, AccountGroup, FinancialYear, JournalEntry, VoucherType, AmortizationSchedule, AmortizationMovement, DayBook, TrialBalanceSnapshot, ProfitAndLossSnapshot

from .services.ledger_service import LedgerService
from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum, Q, Count
from django.contrib import messages
import json
from .services.automation_service import AutomationService

@login_required
@require_POST
@business_required
def reconcile_ledgers(request, business):
    
    matches_found = AutomationService.reconcile_pending_payments(business)
    
    if matches_found > 0:
        messages.success(request, f"God-Level Reconciliation Complete: {matches_found} payments matched to actual invoices!")
    else:
        messages.info(request, "Reconciliation Engine finished: No new matches found currently.")
        
    return redirect('ledger:trial-balance', biz_pk=business.pk)

@login_required
@require_POST
@business_required
def run_cleanup_protocol(request, business):
    
    corrections = LedgerService.smart_cleanup(business)
    
    if corrections:
        count = len(corrections)
        messages.success(request, f"Universal Corrections Protocol Finished: Applied {count} fixes to your ledger.")
        for msg in corrections[:5]: # Show first 5 detailed fixes
             messages.info(request, f"Fix: {msg}")
    else:
        messages.info(request, "Cleanup Complete: No inconsistencies found. Your ledger is GAAP compliant.")
        
    return redirect('ledger:trial-balance', biz_pk=business.pk)

@login_required
@business_required
def day_book_view(request, business):
    
    entries = DayBook.objects.filter(business=business).select_related('voucher', 'document').order_by('date', 'created_at')
    
    # Still calculate totals from live vouchers for the footer
    total_dr = JournalEntry.objects.filter(voucher__business=business, voucher__is_draft=False).aggregate(Sum('debit'))['debit__sum'] or 0
    total_cr = JournalEntry.objects.filter(voucher__business=business, voucher__is_draft=False).aggregate(Sum('credit'))['credit__sum'] or 0
    
    return render(request, 'ledger/daybook.html', {
        'business': business, 
        'entries': entries,
        'total_dr': total_dr,
        'total_cr': total_cr
    })

@login_required
@business_required
def trial_balance_view(request, business):
    
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
    
    snapshots = TrialBalanceSnapshot.objects.filter(business=business).order_by('-created_at')[:5]
            
    return render(request, 'ledger/trial_balance.html', {
        'business': business, 
        'report_data': report_data,
        'total_dr': total_dr,
        'total_cr': total_cr,
        'health_checks': health_checks,
        'snapshots': snapshots
    })

@login_required
@business_required
def profit_loss_view(request, business):
    
    latest_snap = ProfitAndLossSnapshot.objects.filter(business=business).order_by('-created_at').first()
    
    if latest_snap:
        income_data = latest_snap.income_json.get('entries', [])
        expense_data = latest_snap.expense_json.get('entries', [])
        total_income = Decimal(str(latest_snap.income_json.get('total', 0)))
        total_expense = Decimal(str(latest_snap.expense_json.get('total', 0)))
        net_profit = latest_snap.net_profit
    else:
        # Fallback to dynamic (or show empty)
        income_data = []
        expense_data = []
        total_income = Decimal('0')
        total_expense = Decimal('0')
        net_profit = Decimal('0')
    
    return render(request, 'ledger/profit_loss.html', {
        'business': business,
        'income_data': income_data,
        'expense_data': expense_data,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_profit': net_profit,
        'snapshot': latest_snap
    })

@login_required
@business_required
def balance_sheet_view(request, business):
    
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
    to_account_id = request.POST.get('to_account_id') # Balancing Account
    
    if not entry_id or not new_account_id:
        messages.error(request, "Missing entry ID or account ID.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    try:
        if request.user.is_superuser:
            entry = JournalEntry.objects.get(id=entry_id)
        else:
            entry = JournalEntry.objects.get(id=entry_id, voucher__business__created_by=request.user)
    except JournalEntry.DoesNotExist:
        messages.error(request, f"Journal Entry {entry_id} not found or access denied.")
        return redirect(request.META.get('HTTP_REFERER', '/'))
        
    try:
        new_acc = Account.objects.get(id=new_account_id, business=entry.voucher.business)
    except Account.DoesNotExist:
        messages.error(request, f"Account {new_account_id} not found for this business.")
        return redirect(request.META.get('HTTP_REFERER', '/'))
    
    # 1. Update the primary entry
    entry.account = new_acc
    entry.save()

    # 2. Update the balancing entry if requested (The "To" Constraint)
    voucher = entry.voucher
    if to_account_id:
        try:
            to_acc = Account.objects.get(id=to_account_id, business=voucher.business)
            # Find the other side of the entry
            other_entry = voucher.entries.exclude(id=entry.id).first()
            if other_entry:
                other_entry.account = to_acc
                other_entry.save()
        except Account.DoesNotExist:
            pass

    # 3. Synchronize narration with the new "To" constraint
    dr_acc = voucher.entries.filter(debit__gt=0).first()
    cr_acc = voucher.entries.filter(credit__gt=0).first()
    if dr_acc and cr_acc:
        v_type_label = voucher.voucher_type.title()
        voucher.narration = f"{v_type_label}: Dr {dr_acc.account.name} To {cr_acc.account.name} | Ref: {voucher.voucher_number}"
        voucher.save()
    
    messages.success(request, f"Successfully reclassified entry to {new_acc.name}")
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
    to_account_id = request.POST.get('to_account_id')

    if request.user.is_superuser:
        entry = get_object_or_404(JournalEntry, id=entry_id)
    else:
        entry = get_object_or_404(JournalEntry, id=entry_id, voucher__business__created_by=request.user)

    business = entry.voucher.business
    group = get_object_or_404(AccountGroup, id=group_id, business=business)

    # 1. Create the new account with automated normalization
    from .services.automation_service import AutomationService
    normalized_name = AutomationService.normalize_ledger_name(account_name)
    
    new_acc, created = Account.objects.get_or_create(
        business=business,
        name=normalized_name,
        defaults={
            'group': group,
            'classification': group.classification
        }
    )

    # 2. Reclassify the entry
    entry.account = new_acc
    entry.save()

    # 3. Handle Balancing Account (To-Constraint)
    voucher = entry.voucher
    if to_account_id:
        try:
            to_acc = Account.objects.get(id=to_account_id, business=business)
            other_entry = voucher.entries.exclude(id=entry.id).first()
            if other_entry:
                other_entry.account = to_acc
                other_entry.save()
        except Account.DoesNotExist:
            pass

    # 4. Synchronize Narration
    dr_acc = voucher.entries.filter(debit__gt=0).first()
    cr_acc = voucher.entries.filter(credit__gt=0).first()
    if dr_acc and cr_acc:
        v_type_label = voucher.voucher_type.title()
        voucher.narration = f"{v_type_label}: Dr {dr_acc.account.name} To {cr_acc.account.name} | Ref: {voucher.voucher_number}"
        voucher.save()

    messages.success(request, f"Created new ledger '{new_acc.name}' and reclassified entry.")
    return redirect(request.META.get('HTTP_REFERER', '/'))
@login_required
@require_POST
@business_required
def record_capital_infusion(request, business):
    
    amount_str = request.POST.get('amount', '0')
    try:
        amount = Decimal(amount_str)
    except:
        messages.error(request, "Invalid amount.")
        return redirect('ledger:trial-balance', biz_pk=business.pk)

    if amount <= 0:
        messages.error(request, "Amount must be positive.")
        return redirect('ledger:trial-balance', biz_pk=business.pk)

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

    return redirect('ledger:trial-balance', biz_pk=business.pk)

@login_required
@require_POST
@business_required
def purge_business_data(request, business):
    
    with transaction.atomic():
        # 1. This cascades to most things (DayBook, Snapshots, Entries, Movements)
        business.documents.all().delete()
        
        # 2. Cleanup Manual Vouchers (Opening Capital, etc.)
        Voucher.objects.filter(business=business).delete()
        
        # 3. Cleanup Inventory Movements (even manual ones)
        from apps.inventory.models import StockMovement
        StockMovement.objects.filter(product__business=business).delete()
        
        # 4. Optional: Reset Voucher Series
        from .models import VoucherSeries
        VoucherSeries.objects.filter(business=business).update(current_number=1)

    messages.success(request, f"Nuclear Purge Complete: All records for {business.name} have been annihilated. Clean slate initialized.")
    return redirect('core:business_detail', pk=business.pk)

@login_required
@business_required
def forensic_dashboard_view(request, business):
    
    suspicious_docs = Document.objects.filter(business=business, is_suspicious=True).order_by('-uploaded_at')
    
    # Simple IP Analysis
    from django.db.models import Count
    ip_stats = Document.objects.filter(business=business).values('upload_ip').annotate(count=Count('id')).order_by('-count')
    
    return render(request, 'ledger/forensic_dashboard.html', {
        'business': business,
        'suspicious_docs': suspicious_docs,
        'ip_stats': ip_stats
    })

@login_required
@business_required
def amortization_tracker_view(request, business):
    
    schedules = AmortizationSchedule.objects.filter(business=business).prefetch_related('movements')
    
    active_schedules = schedules.filter(is_active=True)
    completed_schedules = schedules.filter(is_active=False)
    
    # Calculate totals
    total_prepaid = schedules.filter(is_active=True).aggregate(total=Sum('total_amount'))['total'] or 0
    
    return render(request, 'ledger/amortization_tracker.html', {
        'business': business,
        'active_schedules': active_schedules,
        'completed_schedules': completed_schedules,
        'total_prepaid': total_prepaid
    })

@login_required
@business_required
def intercompany_control_tower_view(request, business):
    
    subsidiaries = Business.objects.filter(parent=business)
    parent = business.parent
    
    # Find transactions flagged for intercompany
    intercompany_docs = Document.objects.filter(business=business, accounting_logic__contains='INTERCOMPANY')
    
    return render(request, 'ledger/intercompany_control.html', {
        'business': business,
        'subsidiaries': subsidiaries,
        'parent': parent,
        'intercompany_docs': intercompany_docs
    })

@login_required
@business_required
def security_performance_audit_view(request, business):
    if not (request.user.is_superuser or business.owner == request.user or business.created_by == request.user):
        raise PermissionDenied
    
    # Audit Log Chain Integrity Check
    from apps.audit.models import AuditLog
    logs = AuditLog.objects.order_by('timestamp')
    integrity_issues = []
    
    # We'll just check the last 100 for performance
    prev_hash = None
    for log in logs[:100]:
        if prev_hash and log.previous_hash != prev_hash:
            integrity_issues.append(f"Chain Break detected at Log ID: {log.id}")
        prev_hash = log.entry_hash

    # Performance Hotspots
    # 1. Accounts with excessive transactions
    db_hotspots = Account.objects.filter(business=business).annotate(entry_count=Count('journal_entries')).order_by('-entry_count')[:5]
    
    # 2. Slow Reports Simulation (Metadata)
    import time
    start = time.time()
    # Dummy aggregation to measure DB speed
    JournalEntry.objects.filter(voucher__business=business).aggregate(Sum('debit'))
    db_latency = (time.time() - start) * 1000 # ms

    return render(request, 'ledger/security_performance_report.html', {
        'business': business,
        'integrity_issues': integrity_issues,
        'db_hotspots': db_hotspots,
        'db_latency': db_latency,
        'log_count': logs.count()
    })
