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
    def get_time_series_data(business):
        """
        Calculates weekly inflow and outflow for the last 6 weeks.
        """
        import datetime
        from django.db.models.functions import TruncWeek
        
        today = datetime.date.today()
        six_weeks_ago = today - datetime.timedelta(weeks=6)
        
        # Aggregate Inflow (Income Credit - Income Debit)
        inflow = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='INCOME',
            voucher__date__gte=six_weeks_ago
        ).annotate(week=TruncWeek('voucher__date')).values('week').annotate(
            total=Sum('credit') - Sum('debit')
        ).order_by('week')
        
        # Aggregate Outflow (Expense Debit - Expense Credit)
        outflow = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='EXPENSE',
            voucher__date__gte=six_weeks_ago
        ).annotate(week=TruncWeek('voucher__date')).values('week').annotate(
            total=Sum('debit') - Sum('credit')
        ).order_by('week')
        
        # Align data into arrays
        labels = []
        inflow_data = []
        outflow_data = []
        
        # Generate last 6 weeks labels
        week_map = {}
        for i in range(5, -1, -1):
            w = (today - datetime.timedelta(weeks=i)).isocalendar()[1]
            labels.append(f"Week {w}")
            week_start = (today - datetime.timedelta(weeks=i)) - datetime.timedelta(days=(today - datetime.timedelta(weeks=i)).weekday())
            week_map[week_start] = len(labels) - 1
            inflow_data.append(0)
            outflow_data.append(0)
            
        for entry in inflow:
            idx = week_map.get(entry['week'].date())
            if idx is not None:
                inflow_data[idx] = float(entry['total'] or 0)
                
        for entry in outflow:
            idx = week_map.get(entry['week'].date())
            if idx is not None:
                outflow_data[idx] = float(entry['total'] or 0)
                
        return {
            'labels': labels,
            'inflow': inflow_data,
            'outflow': outflow_data
        }

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
            'forensic_warnings': business.documents.filter(is_suspicious=True).count(),
            'active_amortizations': business.amortizationschedules.filter(is_active=True).count(),
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

    @staticmethod
    def get_statutory_calendar(business):
        """
        GOD-MODE: Calculates upcoming Indian statutory deadlines.
        Includes GST (20th), TDS (7th), and MSME (45 days from bill date).
        """
        import datetime
        from core.models import Document
        from django.db.models import Q
        
        today = datetime.date.today()
        deadlines = []

        # 1. GST GSTR-3B (Typically 20th of next month)
        next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=20)
        deadlines.append({
            'title': 'GST GSTR-3B Filing',
            'date': next_month,
            'type': 'GST',
            'description': 'Monthly summary return and tax payment.'
        })

        # 2. TDS Payment (7th of next month)
        next_tds = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=7)
        deadlines.append({
            'title': 'TDS Payment',
            'date': next_tds,
            'type': 'TDS',
            'description': 'Deposit tax deducted at source for the previous month.'
        })

        # 3. MSME Deadlines (Section 43B(h))
        # Find unpaid MSME bills with upcoming 45-day deadlines
        msme_bills = Document.objects.filter(
            business=business,
            is_msme=True,
            payment_deadline__gte=today
        ).order_by('payment_deadline')[:5]

        for bill in msme_bills:
            deadlines.append({
                'title': f'MSME Payment: {bill.document_number}',
                'date': bill.payment_deadline,
                'type': 'MSME',
                'description': f'Mandatory 45-day payment deadline for {bill.lines.first().vendor if bill.lines.exists() else "Vendor"}.'
            })

        return sorted(deadlines, key=lambda x: x['date'])
