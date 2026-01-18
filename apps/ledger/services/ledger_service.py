from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from decimal import Decimal
from ..models import Voucher, JournalEntry, Account, FinancialYear, VoucherSeries, AccountGroup, VoucherType
import datetime
import hashlib

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
        hash(business_id + date + amount + narration_snippet + type)
        """
        # Clean narration to avoid minor variations
        clean_narr = (narration or "")[:20].upper().strip()
        payload = f"{business_id}|{date}|{amount}|{clean_narr}|{voucher_type}"
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
        v_date = voucher_data['date']
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

        # 8. Final Math Balance
        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise ValidationError(f"Accounting Imbalance: Sum Dr ({total_debit}) != Sum Cr ({total_credit})")

        return voucher

    @staticmethod
    def get_or_create_suspense(business):
        group, _ = AccountGroup.objects.get_or_create(
            business=business, 
            name="Current Liabilities",
            defaults={'classification': 'LIABILITY', 'is_revenue_nature': False}
        )
        acc, _ = Account.objects.get_or_create(
            business=business,
            name="Suspense Account",
            group=group
        )
        return acc

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
        
        # 1. Suspense Audit
        suspense = LedgerService.get_or_create_suspense(business)
        bal = LedgerService.get_account_balance(suspense.id)
        if abs(bal) > 0.01:
            checks.append({
                'severity': 'ERROR',
                'message': f"Suspense Account is not zero (₹{bal}). This indicates unresolved cash movements or reclassified entries.",
                'code': 'SUSPENSE_RESIDUAL'
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

        return checks

    @staticmethod
    @transaction.atomic
    def repair_all_vouchers(business):
        """
        CA-Grade Point: 'Regenerate' correct books.
        Audits existing vouchers and auto-corrects them to follow GAAP.
        """
        vouchers = Voucher.objects.filter(business=business)
        corrections = []
        
        # Pre-initialize Suspense
        suspense = LedgerService.get_or_create_suspense(business)
        
        for v in vouchers:
            v_type = v.voucher_type
            v_entries = v.entries.all()
            
            # Rule 1 & 2 Correction: Payment vs Expense
            if v_type == VoucherType.PAYMENT:
                for entry in v_entries:
                    if entry.debit > 0 and entry.account.classification == 'EXPENSE':
                        old_name = entry.account.name
                        entry.account = suspense
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
