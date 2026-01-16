from decimal import Decimal
from django.db import transaction
from apps.ledger.models import Voucher, JournalEntry, Account, FinancialYear, VoucherType
from apps.ledger.services.ledger_service import LedgerService
from core.models import Document, ExtractedLineItem

class AutomationService:
    """
    Service to automate ledger entry creation from processed documents.
    """

    @staticmethod
    def get_or_create_default_account(business, name, group_type='EXPENSE'):
        """
        Ensures a basic account exists for the business.
        """
        from apps.ledger.models import AccountGroup
        
        # Simple heuristic to find or create a group
        group, _ = AccountGroup.objects.get_or_create(
            business=business,
            name=f"Default {group_type}",
            defaults={'classification': group_type}
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
        """
        Converts extracted data from a Document into a Ledger Voucher.
        """
        if document.status != "processed":
            raise ValueError("Document must be processed before ledger conversion.")

        lines = document.lines.all()
        if not lines.exists():
            return None

        # 1. Identify Financial Year
        doc_date = document.document_date or (lines[0].date if lines.exists() else None)
        if not doc_date:
            from datetime import date
            doc_date = date.today()

        fy = FinancialYear.objects.filter(
            business=document.business,
            start_date__lte=doc_date,
            end_date__gte=doc_date
        ).first()

        if not fy:
            from datetime import date
            fy = FinancialYear.objects.create(
                business=document.business,
                start_date=date(doc_date.year, 4, 1),
                end_date=date(doc_date.year + 1, 3, 31)
            )

        # 2. Determine Voucher Type
        v_type = VoucherType.PURCHASE if document.doc_type == 'receipt' else VoucherType.JOURNAL

        # 3. Prepare entries
        entries_data = []
        total_amount = Decimal('0.00')
        
        credit_account = cls.get_or_create_default_account(document.business, "Suspense Account", "LIABILITY")

        for line in lines:
            if not line.amount:
                continue
            
            ledger_name = line.ledger_account or "Uncategorized Expense"
            debit_account = cls.get_or_create_default_account(document.business, ledger_name, "EXPENSE")
            
            entries_data.append({
                'account_id': debit_account.id,
                'debit': line.amount,
                'credit': 0
            })
            total_amount += line.amount

        if total_amount > 0:
            entries_data.append({
                'account_id': credit_account.id,
                'debit': 0,
                'credit': total_amount
            })

            # 4. Use LedgerService to create the voucher
            voucher_data = {
                'voucher_type': v_type,
                'voucher_number': document.document_number or f"AUTO-{document.id}",
                'date': doc_date,
                'fy_id': fy.id,
                'narration': f"Auto-generated from document {document.id}. Vendor: {lines[0].vendor if lines.exists() else 'Unknown'}",
                'is_draft': True
            }

            return LedgerService.create_voucher(document.business, voucher_data, entries_data)
        
        return None
