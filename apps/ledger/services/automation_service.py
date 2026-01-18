from decimal import Decimal
from django.db import transaction
from apps.ledger.models import Voucher, JournalEntry, Account, FinancialYear, VoucherType, AccountGroup
from apps.ledger.services.ledger_service import LedgerService
from core.models import Document, ExtractedLineItem

class AutomationService:
    """
    CA-Grade Automation Service.
    Converts raw documents/statements into GAAP-compliant vouchers.
    """

    @staticmethod
    def get_or_create_default_account(business, name, group_name):
        group = AccountGroup.objects.filter(business=business, name=group_name).first()
        if not group:
            # Classification mapping for Standard Tally Groups
            classification = 'EXPENSE'
            if 'Income' in group_name: classification = 'INCOME'
            elif 'Asset' in group_name or 'Bank' in group_name or 'Debtors' in group_name: classification = 'ASSET'
            elif 'Liabilities' in group_name or 'Creditors' in group_name or 'Taxes' in group_name: classification = 'LIABILITY'
            
            group, _ = AccountGroup.objects.get_or_create(
                business=business, 
                name=group_name,
                defaults={'classification': classification, 'is_revenue_nature': 'Expense' in group_name or 'Income' in group_name}
            )
        
        account, _ = Account.objects.get_or_create(
            business=business,
            name=name,
            group=group
        )
        return account

    @classmethod
    @transaction.atomic
    def convert_document_to_voucher(cls, document: Document):
        if document.status not in ["processed", "ocr_complete"]:
            return None

        lines = document.lines.all()
        if not lines.exists():
            return None

        doc_date = document.document_date or (lines[0].date if lines.exists() else None)
        fy = FinancialYear.objects.filter(
            business=document.business, start_date__lte=doc_date, end_date__gte=doc_date
        ).first()

        if not fy:
            from datetime import date
            fy = FinancialYear.objects.create(
                business=document.business,
                start_date=date(doc_date.year, 4, 1),
                end_date=date(doc_date.year + 1, 3, 31)
            )

        if document.doc_type == 'bank':
            return cls._process_bank_statement(document, fy, lines)
        else:
            return cls._process_invoice(document, fy, lines)

    @classmethod
    def _process_bank_statement(cls, document, fy, lines):
        """
        Processes Bank Statements with Settlement Logic (Point 1).
        Never hits Expenses directly.
        """
        vouchers_created = []
        bank_account = cls.get_or_create_default_account(document.business, "Main Bank Account", "Bank Accounts")

        for line in lines:
            amount = line.debit if (line.debit and line.debit > 0) else line.credit
            if not amount or amount == 0: amount = line.amount or Decimal('0.00')

            is_debit = (line.debit and line.debit > 0)
            v_type = VoucherType.PAYMENT if is_debit else VoucherType.RECEIPT
            
            # --- GAAP ENFORCEMENT: SETTLEMENT VS EVENT ---
            # Payment must debit a Liability (Creditor) or Suspense, NEVER Expense.
            
            entries_data = []
            desc = (line.description or "").upper()
            
            # 1. Try to find a Creditor/Debtor
            party_account = None
            
            # Keyword matching now maps to Vendors (Sundry Creditors) for Payments
            vendor_map = {
                'AWS': 'Amazon Web Services',
                'GOOGLE': 'Google Cloud India',
                'SWIGGY': 'Bundl Technologies',
                'RENT': 'Office Landlord',
                'SALARY': 'Staff Salary Payable',
            }
            
            for key, vendor in vendor_map.items():
                if key in desc:
                    party_group = "Sundry Creditors" if is_debit else "Sundry Debtors"
                    party_account = cls.get_or_create_default_account(document.business, vendor, party_group)
                    break
            
            if not party_account:
                # Rule: If payment is unidentified, it MUST go to Suspense
                party_account = LedgerService.get_or_create_suspense(document.business)

            if is_debit:
                # Dr Party (Settlement), Cr Bank
                entries_data.append({'account_id': party_account.id, 'debit': amount, 'credit': 0})
                entries_data.append({'account_id': bank_account.id, 'debit': 0, 'credit': amount})
            else:
                # Dr Bank, Cr Party (Settlement)
                entries_data.append({'account_id': bank_account.id, 'debit': amount, 'credit': 0})
                entries_data.append({'account_id': party_account.id, 'debit': 0, 'credit': amount})

            voucher_data = {
                'voucher_type': v_type,
                'date': line.date or document.document_date,
                'fy_id': fy.id,
                'narration': f"Settlement: {line.description}",
                'is_draft': True,
                'utr_number': line.invoice_no,
                'document_id': document.id
            }
            
            try:
                vouchers_created.append(LedgerService.create_voucher(document.business, voucher_data, entries_data))
            except Exception as e:
                print(f"Automation Bypass: {e}")

        return vouchers_created

    @classmethod
    def _process_invoice(cls, document, fy, lines):
        """
        Processes Invoices with Expense Recognition Logic (Point 1).
        Hits Expenses and GST Asset ledgers.
        """
        is_purchase = True # Default for now
        v_type = VoucherType.PURCHASE if is_purchase else VoucherType.SALES

        total_amount = sum(line.amount for line in lines if line.amount)
        if total_amount == 0: return None

        vendor_name = lines[0].vendor or "Generic Vendor"
        party_group = "Sundry Creditors" if is_purchase else "Sundry Debtors"
        party_account = cls.get_or_create_default_account(document.business, vendor_name, party_group)
        
        entries_data = []
        
        for line in lines:
            if not line.amount: continue
            
            # Expense Recognition (Hitting P&L)
            expense_group = "Indirect Expenses" if is_purchase else "Indirect Incomes"
            expense_acc = cls.get_or_create_default_account(document.business, line.ledger_account or "Purchase Ledger", expense_group)
            
            # Back-calculate Tax (Rule 6: GST != Expense)
            gst_rate_str = (line.gst_rate or "0").replace('%', '')
            try:
                gst_pct = Decimal(gst_rate_str)
            except:
                gst_pct = Decimal('0')
            
            base_amount = line.amount / (1 + (gst_pct/100))
            tax_total = line.amount - base_amount

            # Dr Expense
            entries_data.append({'account_id': expense_acc.id, 'debit': base_amount if is_purchase else 0, 'credit': 0 if is_purchase else base_amount})

            # Rule 6: Input GST -> Asset (Liability side but debit balance)
            if tax_total > 0:
                tax_acc = cls.get_or_create_default_account(document.business, f"Input GST {gst_pct}%", "Duties & Taxes")
                entries_data.append({'account_id': tax_acc.id, 'debit': tax_total if is_purchase else 0, 'credit': 0 if is_purchase else tax_total})

        # Cr Creditor (Creating Payable)
        entries_data.append({
            'account_id': party_account.id, 
            'debit': 0 if is_purchase else total_amount, 
            'credit': total_amount if is_purchase else 0,
            'ref_type': 'NEW',
            'ref_number': getattr(document, 'document_number', f"INV-{document.id}")
        })

        voucher_data = {
            'voucher_type': v_type,
            'date': document.document_date or lines[0].date,
            'fy_id': fy.id,
            'narration': f"Event: {document.doc_type} generated purchase",
            'is_draft': True,
            'document_id': document.id
        }

        return LedgerService.create_voucher(document.business, voucher_data, entries_data)