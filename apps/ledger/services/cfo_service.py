from decimal import Decimal
from django.db.models import Sum
from ..models import Account, JournalEntry, Voucher, VoucherType
from .ledger_service import LedgerService

class CFOService:
    """
    Elite CFO Analysis Service.
    Provides Executive insights: Burn Rate, Tax Savings, and Net P/L.
    """

    @staticmethod
    def get_executive_summary(business):
        """
        Generates the mission-critical financial summary.
        """
        # 1. Burn Rate (Total Operational Expenses in current FY)
        expenses = Account.objects.filter(business=business, group__classification='EXPENSE')
        total_burn = Decimal('0.00')
        for acc in expenses:
            # We use the absolute balance of expense accounts
            bal = LedgerService.get_account_balance(acc.id, business=business)
            total_burn += abs(bal)

        # 2. Tax Savings (Total GST Input Tax Credit found)
        # We look for 'Duties & Taxes' group with 'Input' in name
        tax_accounts = Account.objects.filter(
            business=business, 
            group__name='Duties & Taxes',
            name__icontains='Input'
        )
        total_itc = Decimal('0.00')
        for acc in tax_accounts:
            bal = LedgerService.get_account_balance(acc.id, business=business)
            # ITC is a Debit balance in Duties & Taxes (Asset nature for the user)
            if bal > 0:
                total_itc += bal

        # 3. Net Profit/Loss
        income_accounts = Account.objects.filter(business=business, group__classification='INCOME')
        total_income = Decimal('0.00')
        for acc in income_accounts:
            bal = LedgerService.get_account_balance(acc.id, business=business)
            # Income usually has a Credit balance (negative in our LedgerService math Dr-Cr)
            total_income += abs(bal) if bal < 0 else 0

        net_pl = total_income - total_burn

        return {
            'burn_rate': total_burn,
            'tax_savings': total_itc,
            'net_profit_loss': net_pl,
            'is_profitable': net_pl > 0,
            'itc_count': tax_accounts.count(),
            'expense_count': expenses.count()
        }

    @staticmethod
    def get_compliance_status(business):
        """
        Checks for audit-readiness.
        """
        health = LedgerService.get_accounting_health_checks(business)
        critical_issues = [c for c in health if c['severity'] == 'CRITICAL']
        
        return {
            'is_audit_ready': len(critical_issues) == 0,
            'health_score': max(0, 100 - (len(health) * 10)),
            'issues': health
        }
