from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from decimal import Decimal
from ..models import Voucher, JournalEntry, Account, FinancialYear, VoucherSeries, AccountGroup, VoucherType, DayBook, TrialBalanceSnapshot, ProfitAndLossSnapshot
import datetime
import hashlib
from apps.ledger.services.utils import LedgerCommonUtils

class LedgerService:
    @staticmethod
    def get_next_voucher_number(business, voucher_type):
        """
        Generates the next number in the series for a voucher type.
        """
        series, created = VoucherSeries.objects.get_or_create(
            business=business,
            voucher_type=voucher_type,
            is_active=True,
            defaults={'prefix': f"{voucher_type[:3]}/", 'current_number': 1}
        )
        
        num_str = str(series.current_number).zfill(4)
        v_num = f"{series.prefix}{num_str}{series.suffix}"
        
        # Increment for next time
        series.current_number += 1
        series.save()
        
        return v_num

    @staticmethod
    def generate_fingerprint(business_id, date, amount, narration="", voucher_type=""):
        """
        CA-Grade Point: Idempotency / Duplicate Control
        hash(business_id + date + amount + sanitized_narration + type)
        """
        # Clean narration aggressively: Remove digits, special chars, and extra spaces
        # (Mistake: REC/0024 Duplicate detection failed likely due to minor narration drift)
        import re
        clean_narr = re.sub(r'[^A-Z]', '', (narration or "").upper())
        # Use first 30 alpha chars as the stable anchor
        clean_narr = clean_narr[:30]
        
        payload = f"{business_id}|{date}|{amount:.2f}|{clean_narr}|{voucher_type}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    @transaction.atomic
    def create_voucher(business, voucher_data, entries_data):
        """
        Strict Indian GAAP & Tally-style double-entry bookkeeping engine.
        Enforces Rule-based posting matrix.
        """
        # 1. FY Check
        fy = FinancialYear.objects.get(id=voucher_data['fy_id'], business=business)
        if fy.is_locked:
            raise ValidationError("Locked Financial Year: Cannot modify records.")

        # 2. Date Validation
        v_date = voucher_data.get('date')
        if not v_date:
            raise ValidationError("Transaction Date is required for bookkeeping.")

        if isinstance(v_date, str):
            v_date = datetime.datetime.strptime(v_date, "%Y-%m-%d").date()
            
        if not (fy.start_date <= v_date <= fy.end_date):
            raise ValidationError(f"Invalid Date: {v_date} is outside FY {fy.start_date} to {fy.end_date}")

        v_type = voucher_data['voucher_type']
        
        # 3. Calculate Totals and Fingerprint
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        for e in entries_data:
            total_debit += Decimal(str(e.get('debit', 0)))
            total_credit += Decimal(str(e.get('credit', 0)))

        # Rule Audit: Fingerprint for Deduplication
        fingerprint = voucher_data.get('fingerprint')
        if not fingerprint:
            fingerprint = LedgerService.generate_fingerprint(
                business.id, v_date, total_debit or total_credit, 
                voucher_data.get('narration', ''), v_type
            )

        if Voucher.objects.filter(business=business, fingerprint=fingerprint).exists():
            existing = Voucher.objects.filter(business=business, fingerprint=fingerprint).first()
            raise ValidationError(f"Duplicate Registry: Transaction identical to {existing.voucher_type} #{existing.voucher_number} found.")

        # 4. Strict Semantics Validation (Indian GAAP Rules)
        for entry in entries_data:
            acc = Account.objects.get(id=entry['account_id'], business=business)
            classification = acc.classification
            debit = Decimal(str(entry.get('debit', 0)))
            credit = Decimal(str(entry.get('credit', 0)))

            # RULE: Payment vouchers must NEVER debit expense ledgers
            if v_type == VoucherType.PAYMENT and debit > 0:
                if classification == 'EXPENSE':
                     # AUTO-CORRECT: Redirect to Suspense if detected
                     suspense = LedgerService.get_or_create_suspense(business)
                     entry['account_id'] = suspense.id
                     voucher_data['narration'] = (voucher_data.get('narration', '') + 
                        f" [RECLASSIFIED: Direct expense payment forbidden, moved to {suspense.name}]").strip()
                     acc = suspense # Update for subsequent checks

            # RULE: GST Input Credits can only be recorded in PURCHASE/JOURNAL
            if classification == 'LIABILITY' and 'GST' in acc.name.upper() and debit > 0:
                if v_type not in [VoucherType.PURCHASE, VoucherType.JOURNAL]:
                    raise ValidationError(f"GST Compliance Error: Input Tax Credit on '{acc.name}' can only be recognized via Purchase or Journal vouchers.")

        # 5. Voucher Numbering
        v_num = voucher_data.get('voucher_number')
        if not v_num:
            v_num = LedgerService.get_next_voucher_number(business, v_type)

        # 6. Create Voucher Header
        voucher = Voucher.objects.create(
            business=business,
            financial_year=fy,
            voucher_type=v_type,
            voucher_number=v_num,
            date=v_date,
            narration=voucher_data.get('narration', ''),
            is_draft=voucher_data.get('is_draft', True),
            utr_number=voucher_data.get('utr_number'),
            cheque_number=voucher_data.get('cheque_number'),
            document_id=voucher_data.get('document_id'),
            fingerprint=fingerprint
        )

        # 7. Create Entries
        for entry in entries_data:
            JournalEntry.objects.create(
                voucher=voucher,
                account_id=entry['account_id'],
                debit=Decimal(str(entry.get('debit', 0))),
                credit=Decimal(str(entry.get('credit', 0))),
                ref_type=entry.get('ref_type'),
                ref_number=entry.get('ref_number')
            )

        # 8. Create Day Book Entry (Flattened Perspective)
        from apps.ledger.models import DayBook
        dr_parts = [e.account.name for e in voucher.entries.filter(debit__gt=0)]
        cr_parts = [e.account.name for e in voucher.entries.filter(credit__gt=0)]
        particulars = f"Dr {', '.join(dr_parts)} To {', '.join(cr_parts)}"
        
        DayBook.objects.create(
            business=business,
            document=voucher.document,
            voucher=voucher,
            date=voucher.date,
            particulars=particulars,
            amount=total_debit or total_credit
        )

        # 9. Final Math Balance
        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise ValidationError(f"Accounting Imbalance: Sum Dr ({total_debit}) != Sum Cr ({total_credit})")

        return voucher

    @staticmethod
    def get_or_create_pending_classification(business):
        group, _ = AccountGroup.objects.get_or_create(
            business=business, 
            name="Current Liabilities",
            defaults={'classification': 'LIABILITY', 'is_revenue_nature': False}
        )
        acc, _ = Account.objects.get_or_create(
            business=business,
            name="Pending Classification",
            group=group
        )
        return acc

    @staticmethod
    def get_or_create_suspense(business):
        group, _ = AccountGroup.objects.get_or_create(
            business=business, 
            name="Suspense Accounts",
            defaults={'classification': 'LIABILITY', 'is_revenue_nature': False}
        )
        acc, _ = Account.objects.get_or_create(
            business=business, 
            name="Suspense Account",
            group=group
        )
        return acc

    @staticmethod
    def initialize_financial_year(business):
        """
        Creates the current financial year (April to March) for the business.
        """
        return LedgerCommonUtils.get_financial_year(business, datetime.date.today())

    @staticmethod
    def initialize_standard_coa(business):
        """
        Point 8: Chart of Accounts Guardrails
        """
        groups = [
            ('Assets', 'ASSET', False, None),
            ('Liabilities', 'LIABILITY', False, None),
            ('Income', 'INCOME', True, None),
            ('Expenses', 'EXPENSE', True, None),
            ('Current Assets', 'ASSET', False, 'Assets'),
            ('Bank Accounts', 'ASSET', False, 'Current Assets'),
            ('Sundry Debtors', 'ASSET', False, 'Current Assets'),
            ('Current Liabilities', 'LIABILITY', False, 'Liabilities'),
            ('Sundry Creditors', 'LIABILITY', False, 'Current Liabilities'),
            ('Duties & Taxes', 'LIABILITY', False, 'Current Liabilities'),
            ('Indirect Expenses', 'EXPENSE', True, 'Expenses'),
            ('Indirect Incomes', 'INCOME', True, 'Income'),
        ]
        
        created_groups = {}
        for name, classification, revenue, parent_name in groups:
            parent = created_groups.get(parent_name)
            group, _ = AccountGroup.objects.get_or_create(
                business=business,
                name=name,
                defaults={
                    'classification': classification,
                    'is_revenue_nature': revenue,
                    'parent': parent,
                    'is_reserved': True
                }
            )
            created_groups[name] = group
            
        return list(created_groups.values())

    @staticmethod
    def get_account_balance(account_id, business=None):
        lookup = {"id": account_id}
        if business:
            lookup["business"] = business
            
        acc = Account.objects.get(**lookup)
        entries = JournalEntry.objects.filter(account=acc)
        totals = entries.aggregate(dr_sum=Sum('debit'), cr_sum=Sum('credit'))
        
        balance = acc.opening_balance + (totals['dr_sum'] or Decimal('0.00')) - (totals['cr_sum'] or Decimal('0.00'))
        return balance

    @staticmethod
    def get_pnl_balance(account_id, business=None):
        """
        CA-Grade Point: P&L must include only income and expense ledgers, 
        EXCLUDING bank, creditors, suspense, and GST.
        """
        lookup = {"id": account_id}
        if business:
            lookup["business"] = business
        
        acc = Account.objects.get(**lookup)
        
        # Rule Check: Only Income/Expense classified accounts hit P&L
        if acc.classification not in ['INCOME', 'EXPENSE']:
            return Decimal('0.00')

        # EXCLUSION RULE: Specific accounts that are Revenue Nature but should be ignored 
        # (Though per GAAP, if it's P&L, it's Income/Expense. Bank/Creditors are ASSET/LIABILITY)
        
        pnl_vouchers = [VoucherType.SALES, VoucherType.PURCHASE, VoucherType.JOURNAL, VoucherType.CREDIT_NOTE, VoucherType.DEBIT_NOTE]
        
        entries = JournalEntry.objects.filter(
            account=acc, 
            voucher__voucher_type__in=pnl_vouchers,
            voucher__is_draft=False
        )
        
        totals = entries.aggregate(dr_sum=Sum('debit'), cr_sum=Sum('credit'))
        balance = (totals['dr_sum'] or Decimal('0.00')) - (totals['cr_sum'] or Decimal('0.00'))
        return balance

    @staticmethod
    def get_accounting_health_checks(business):
        checks = []
        
        # 1. Pending Classification Audit (Elite CFO Protocol)
        # Point: Aggregate all variations (Debit/Credit/Suffixes) for a true protocol check
        pending_balances = Account.objects.filter(
            business=business, 
            name__icontains="Pending Classification"
        )
        
        total_pending_bal = Decimal('0.00')
        for acc in pending_balances:
            total_pending_bal += LedgerService.get_account_balance(acc.id)
            
        if abs(total_pending_bal) > 0.01:
            checks.append({
                'severity': 'ERROR',
                'message': f"Pending Classification is not zero (₹{total_pending_bal}). This indicates unresolved cash movements in bank statements needing invoice reconciliation.",
                'code': 'PENDING_RESIDUAL'
            })

        # 2. Duplicate Detection
        duplicates = Voucher.objects.filter(business=business).values('fingerprint').annotate(count=Sum('id')).filter(count__gt=1)
        if duplicates.exists():
             checks.append({
                'severity': 'CRITICAL',
                'message': "Data Integrity Violation: Multiple vouchers sharing the same fingerprint detected.",
                'code': 'FINGERPRINT_COLLISION'
            })

        # 3. Accrual Integrity Check
        # Check for expenses hit via Payment instead of Purchase
        # (Already prevented in create_voucher, but checking existing data)
        payment_expenses = JournalEntry.objects.filter(
            voucher__business=business,
            voucher__voucher_type=VoucherType.PAYMENT,
            account__classification='EXPENSE',
            debit__gt=0
        )
        if payment_expenses.exists():
            checks.append({
                'severity': 'CRITICAL',
                'message': f"{payment_expenses.count()} expenses were recorded directly via Payment. This violates Accrual Accounting.",
                'code': 'PAYMENT_EXPENSE_DIRECT'
            })

        # 4. Financial Health Guardrails (Professional Alerts)
        total_assets = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='ASSET',
            voucher__is_draft=False
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        
        asset_bal = (total_assets['dr'] or Decimal('0')) - (total_assets['cr'] or Decimal('0'))
        if asset_bal <= 0:
             checks.append({
                'severity': 'WARNING',
                'message': "Incomplete Books: Total Assets are ₹0 or negative. Opening bank balance or capital infusion likely missing.",
                'code': 'ZERO_ASSET_BASE'
            })

        # Calculate Equity/Net Worth (Total Assets - Total Liabilities)
        total_liab = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='LIABILITY',
            voucher__is_draft=False
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        
        liab_bal = (total_liab['cr'] or Decimal('0')) - (total_liab['dr'] or Decimal('0'))
        
        if asset_bal < liab_bal:
            checks.append({
                'severity': 'WARNING',
                'message': "Negative Equity Alert: Your liabilities exceed your assets. Possible missing capital records or severe operational loss.",
                'code': 'NEGATIVE_EQUITY'
            })

        # 5. Forensic Shield Health Checks (GOD-MODE)
        from core.models import Document
        suspicious_docs = Document.objects.filter(business=business, is_suspicious=True)
        if suspicious_docs.exists():
            checks.append({
                'severity': 'CRITICAL',
                'message': f"Forensic Alert: {suspicious_docs.count()} documents have been flagged for metadata anomalies or IP mismatches (Potential Fraud).",
                'code': 'FORENSIC_SUSPICION'
            })

        # 6. Intercompany Mismatch (Symmetry Audit)
        if business.is_intercompany_enabled:
            # Check for high-value transactions without Intercompany Sync note
            unsynced_docs = Document.objects.filter(
                business=business,
                is_processed=True
            ).exclude(accounting_logic__icontains="[Intercompany Sync]")
            
            # (Just a simple indicator for now, can be expanded to full cross-entity query)
            pass

        return checks

    @staticmethod
    @transaction.atomic
    def smart_cleanup(business):
        """
        UNIVERSAL CORRECTIONS PROTOCOL (Section 7)
        1. Fixes naming/typos.
        2. Merges duplicate accounts.
        3. Identifies and removes duplicate vouchers like REC/0024.
        """
        from apps.ledger.services.automation_service import AutomationService
        corrections = []
        
        # 1. Account Cleanup (Naming & Merging)
        accounts = Account.objects.filter(business=business)
        name_map = {} # normalized_name -> list of account objects
        
        for acc in accounts:
            old_name = acc.name
            new_name = LedgerCommonUtils.normalize_ledger_name(old_name)
            
            if old_name != new_name:
                acc.name = new_name
                acc.save()
                corrections.append(f"Fixed account name: '{old_name}' -> '{new_name}'")
            
            # Group for merging duplicates (Section 2.2)
            if new_name not in name_map:
                name_map[new_name] = []
            name_map[new_name].append(acc)
            
        # 2. Merge Duplicate Accounts (Section 2.2)
        for name, acc_list in name_map.items():
            if len(acc_list) > 1:
                primary = acc_list[0]
                duplicates = acc_list[1:]
                for dup in duplicates:
                    # Point: Transfer all transactions to primary (Step 3 of Section 2.2)
                    JournalEntry.objects.filter(account=dup).update(account=primary)
                    corrections.append(f"Merged duplicate account {dup.id} into {primary.name}")
                    dup.delete()

        # 3. Duplicate Voucher Elimination (Section 2.2)
        # Specifically targeting REC/0024 logic and general fingerprints
        vouchers = Voucher.objects.filter(business=business).order_by('created_at')
        fp_map = {}
        for v in vouchers:
            # Re-calculate fingerprint with the new aggressive logic
            fp = LedgerService.generate_fingerprint(business.id, v.date, v.total_amount, v.narration, v.voucher_type)
            if v.fingerprint != fp:
                v.fingerprint = fp
                v.save()
                
            if fp in fp_map:
                v_num = v.voucher_number
                corrections.append(f"Deleted duplicate voucher: {v_num} (Matches {fp_map[fp]})")
                v.delete()
            else:
                fp_map[fp] = v.voucher_number

        # 4. Narration Polish (Section 2.1)
        for v in Voucher.objects.filter(business=business):
            if v.narration:
                old_n = v.narration
                # Correcting common narration typos or messy formatting
                new_n = old_n.replace(" / ", "/").replace(" - ", "-")
                if " [REPAIRED" in new_n: continue # Skip already corrected
                
                if old_n != new_n:
                    v.narration = new_n
                    v.save()
        
        return corrections

    @staticmethod
    @transaction.atomic
    def repair_all_vouchers(business):
        """
        Elite CFO Protocol: Reset existing accounting data to GAAP-compliance.
        Enforces strict Point 1 boundaries.
        """
        vouchers = Voucher.objects.filter(business=business)
        corrections = []
        
        # Pre-initialize Pending Classification
        pending_acc = LedgerService.get_or_create_pending_classification(business)
        
        for v in vouchers:
            v_type = v.voucher_type
            v_entries = v.entries.all()
            
            # Rule 1 & 2 Correction: Payment vs Expense
            if v_type == VoucherType.PAYMENT:
                for entry in v_entries:
                    if entry.debit > 0 and entry.account.classification == 'EXPENSE':
                        old_name = entry.account.name
                        entry.account = pending_acc
                        entry.save()
                        
                        v.narration = f"{v.narration} [REPAIRED: Moved {old_name} debit to Suspense (GAAP Violation)]".strip()
                        v.save()
                        corrections.append(f"Vch {v.voucher_number}: Moved Expense payment to Suspense.")

            # Ensure Fingerprint exists and is unique
            new_fingerprint = LedgerService.generate_fingerprint(
                business.id, v.date, v.total_amount, 
                v.narration, v.voucher_type
            )
            
            if v.fingerprint != new_fingerprint:
                if Voucher.objects.filter(business=business, fingerprint=new_fingerprint).exclude(id=v.id).exists():
                    v_num = v.voucher_number
                    v.delete()
                    corrections.append(f"Deleted duplicate voucher {v_num}.")
                else:
                    v.fingerprint = new_fingerprint
                    v.save()

        return corrections

    @staticmethod
    def generate_financial_snapshots(business, document=None):
        """
        GOD-MODE: Captures the entire financial state into persistent models.
        """
        today = datetime.date.today()
        
        # 1. Trial Balance Snapshot
        balances = JournalEntry.objects.filter(
            voucher__business=business, 
            voucher__is_draft=False
        ).values('account_id', 'account__name', 'account__group__name').annotate(
            dr_total=Sum('debit'),
            cr_total=Sum('credit')
        )
        
        tb_data = []
        total_dr = Decimal('0.00')
        total_cr = Decimal('0.00')
        
        # Include opening balances
        accounts = Account.objects.filter(business=business).select_related('group')
        bal_map = {b['account_id']: (b['dr_total'] or Decimal('0')) - (b['cr_total'] or Decimal('0')) for b in balances}
        
        for acc in accounts:
            movement = bal_map.get(acc.id, Decimal('0'))
            bal = acc.opening_balance + movement
            if bal != 0:
                dr = bal if bal > 0 else 0
                cr = -bal if bal < 0 else 0
                tb_data.append({
                    'account': acc.name,
                    'group': acc.group.name,
                    'debit': float(dr),
                    'credit': float(cr)
                })
                total_dr += dr
                total_cr += cr
        
        TrialBalanceSnapshot.objects.create(
            business=business,
            document=document,
            date=today,
            total_debit=total_dr,
            total_credit=total_cr,
            is_balanced=abs(total_dr - total_cr) < 0.01,
            data_snapshot={'entries': tb_data}
        )

        # 2. Profit & Loss Snapshot
        # (Simplified period: Current Financial Year)
        fy = LedgerService.initialize_financial_year(business)
        
        pnl_balances = JournalEntry.objects.filter(
            voucher__business=business,
            voucher__is_draft=False,
            account__group__classification__in=['INCOME', 'EXPENSE']
        ).values('account_id', 'account__name', 'account__group__classification').annotate(dr=Sum('debit'), cr=Sum('credit'))
        
        income_data = []
        expense_data = []
        total_inc = Decimal('0')
        total_exp = Decimal('0')
        
        for b in pnl_balances:
            bal = (b['dr'] or Decimal('0')) - (b['cr'] or Decimal('0'))
            if b['account__group__classification'] == 'INCOME':
                actual_bal = -bal
                income_data.append({'name': b['account__name'], 'amount': float(actual_bal)})
                total_inc += actual_bal
            else:
                expense_data.append({'name': b['account__name'], 'amount': float(bal)})
                total_exp += bal
                
        ProfitAndLossSnapshot.objects.create(
            business=business,
            document=document,
            period_start=fy.start_date,
            period_end=fy.end_date,
            net_profit=total_inc - total_exp,
            income_json={'entries': income_data, 'total': float(total_inc)},
            expense_json={'entries': expense_data, 'total': float(total_exp)}
        )

    @staticmethod
    @transaction.atomic
    def post_scheduled_amortizations(business, target_date=None):
        """
        Sweeps all active AmortizationSchedules and posts monthly journals.
        Ref: ERR-005, 101, 151
        """
        from apps.ledger.models import AmortizationSchedule, AmortizationMovement, Voucher, VoucherType
        from django.utils import timezone
        
        if not target_date:
            target_date = datetime.date.today()
            
        movements = AmortizationMovement.objects.filter(
            schedule__business=business,
            schedule__is_active=True,
            date__lte=target_date,
            is_posted=False
        ).select_related('schedule', 'schedule__asset_account', 'schedule__expense_account', 'schedule__voucher__financial_year')
        
        posted_count = 0
        for move in movements:
            schedule = move.schedule
            asset_acc = schedule.asset_account
            expense_acc = schedule.expense_account
            amount = move.amount
            
            # Create the Journal Voucher
            voucher_data = {
                'voucher_type': VoucherType.JOURNAL,
                'date': move.date,
                'fy_id': schedule.voucher.financial_year_id,
                'narration': f"Amortization: Monthly release from {asset_acc.name} to {expense_acc.name}",
                'is_draft': False # Posting definitively
            }
            
            # Dr Expense, Cr Asset
            entries_data = [
                {'account_id': expense_acc.id, 'debit': amount, 'credit': 0},
                {'account_id': asset_acc.id, 'debit': 0, 'credit': amount}
            ]
            
            try:
                vch = LedgerService.create_voucher(business, voucher_data, entries_data)
                move.journal_voucher = vch
                move.is_posted = True
                move.save()
                posted_count += 1
            except Exception as e:
                print(f"Failed to post amortization {move.id}: {e}")
                
        return posted_count

