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
        # Professional optimization: Use one query instead of iterating
        expense_totals = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='EXPENSE'
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        
        total_burn = (expense_totals['dr'] or Decimal('0.00')) - (expense_totals['cr'] or Decimal('0.00'))

        # 2. Tax Savings (Total GST Input Tax Credit found)
        itc_totals = JournalEntry.objects.filter(
            account__business=business, 
            account__group__name='Duties & Taxes',
            account__name__icontains='Input'
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        
        total_itc = (itc_totals['dr'] or Decimal('0.00')) - (itc_totals['cr'] or Decimal('0.00'))

        # 3. Net Profit/Loss
        income_totals = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='INCOME'
        ).aggregate(dr=Sum('debit'), cr=Sum('credit'))
        
        total_income = (income_totals['cr'] or Decimal('0.00')) - (income_totals['dr'] or Decimal('0.00'))
        net_pl = total_income - total_burn

        return {
            'burn_rate': total_burn,
            'tax_savings': total_itc,
            'net_profit_loss': net_pl,
            'total_income': total_income,
            'total_expense': total_burn,
            'net_profit': net_pl,
            'is_profitable': net_pl > 0,
            'itc_count': Account.objects.filter(business=business, group__name='Duties & Taxes', name__icontains='Input').count(),
            'expense_count': Account.objects.filter(business=business, group__classification='EXPENSE').count(),
            'health_checks': LedgerService.get_accounting_health_checks(business)
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
