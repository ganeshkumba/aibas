from django.db import models
from django.core.exceptions import ValidationError
from core.models import Business, Document
from apps.common.models import BusinessOwnedModel
import uuid

class FinancialYear(BusinessOwnedModel):
    start_date = models.DateField()
    end_date = models.DateField()
    is_locked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.business.name}: {self.start_date.year}-{self.end_date.year}"

class AccountGroup(BusinessOwnedModel):
    """
    Hierarchical groups for the Chart of Accounts.
    Example: Assets -> Current Assets -> Bank Accounts
    """
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subgroups')
    
    # Standard Accounting Classification
    class Classification(models.TextChoices):
        ASSET = 'ASSET', 'Asset'
        LIABILITY = 'LIABILITY', 'Liability'
        EQUITY = 'EQUITY', 'Equity'
        INCOME = 'INCOME', 'Income'
        EXPENSE = 'EXPENSE', 'Expense'
    
    classification = models.CharField(max_length=20, choices=Classification.choices)
    
    # Whether this group belongs to Balance Sheet or P&L
    is_revenue_nature = models.BooleanField(default=False, help_text="True for P&L items (Income/Expense), False for Balance Sheet")
    
    # Reserved names for Tally-like groups
    is_reserved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.classification})"

class Account(BusinessOwnedModel):
    """
    The actual Ledger Account.
    """
    group = models.ForeignKey(AccountGroup, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True) # Optional accounting code
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    
    # Fixed nature derived from group at creation
    classification = models.CharField(max_length=20, choices=AccountGroup.Classification.choices, default='ASSET', db_index=True)
    is_system_reserved = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['business', 'classification']),
            models.Index(fields=['business', 'group']),
        ]

    def save(self, *args, **kwargs):
        if not self.pk or not self.classification:
            self.classification = self.group.classification
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} | {self.group.name}"
    
    def get_outstanding_bills(self):
        """
        Returns a list of bill references and their remaining balances.
        """
        from django.db.models import Sum
        from .models import JournalEntry
        
        # Aggregate by reference number
        bill_data = JournalEntry.objects.filter(account=self).values('ref_number').annotate(
            total_dr=Sum('debit'),
            total_cr=Sum('credit')
        ).exclude(ref_number__isnull=True)
        
        outstandings = []
        for bill in bill_data:
            balance = bill['total_dr'] - bill['total_cr']
            if abs(balance) > 0.01:
                outstandings.append({
                    'ref_number': bill['ref_number'],
                    'balance': balance,
                    'type': 'Dr' if balance > 0 else 'Cr'
                })
        return outstandings

class VoucherType(models.TextChoices):
    SALES = 'SALES', 'Sales'
    PURCHASE = 'PURCHASE', 'Purchase'
    PAYMENT = 'PAYMENT', 'Payment'
    RECEIPT = 'RECEIPT', 'Receipt'
    CONTRA = 'CONTRA', 'Contra'
    JOURNAL = 'JOURNAL', 'Journal'
    CREDIT_NOTE = 'CREDIT_NOTE', 'Credit Note'
    DEBIT_NOTE = 'DEBIT_NOTE', 'Debit Note'

class VoucherSeries(BusinessOwnedModel):
    """
    Defines numbering schemes for different voucher types.
    Example: Prefix='PUR/', Suffix='/23-24', StartNumber=1, Padding=3 -> PUR/001/23-24
    """
    voucher_type = models.CharField(max_length=20, choices=VoucherType.choices)
    prefix = models.CharField(max_length=20, blank=True)
    suffix = models.CharField(max_length=20, blank=True)
    current_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('business', 'voucher_type', 'prefix')

class Voucher(BusinessOwnedModel):
    """
    Header for a transaction.
    """
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True, related_name='vouchers')
    voucher_type = models.CharField(max_length=20, choices=VoucherType.choices)
    voucher_number = models.CharField(max_length=50) # Auto-generated per type/business
    date = models.DateField()
    narration = models.TextField(blank=True)
    
    # Added for Bank Statement & Tally logic
    utr_number = models.CharField(max_length=100, blank=True, null=True)
    cheque_number = models.CharField(max_length=50, blank=True, null=True)

    is_draft = models.BooleanField(default=True) # AI drafts start here
    
    # Forensic / Dedup properties
    fingerprint = models.CharField(max_length=255, unique=True, null=True, blank=True, 
                               help_text="hash(vendor + invoice_no + date + total_amount)")
    
    class Meta:
        unique_together = ('business', 'voucher_type', 'voucher_number', 'financial_year')
        indexes = [
            models.Index(fields=['business', 'date']),
            models.Index(fields=['business', 'voucher_type']),
            models.Index(fields=['business', 'is_draft']),
            models.Index(fields=['date']),
        ]

    @property
    def total_amount(self):
        from decimal import Decimal
        return sum(e.debit for e in self.entries.all()) or Decimal('0.00')

    def __str__(self):
        return f"{self.voucher_type} #{self.voucher_number} | {self.date}"

class JournalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='journal_entries')
    
    debit = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, db_index=True)
    credit = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, db_index=True)
    
    # Added for Bill Wise Allocation (Tally)
    REF_TYPES = [
        ('NEW', 'New Ref'),
        ('AGST', 'Against Ref'),
        ('ADV', 'Advance'),
        ('ON_ACC', 'On Account'),
    ]
    ref_type = models.CharField(max_length=10, choices=REF_TYPES, blank=True, null=True)
    ref_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
    class Meta:
        verbose_name_plural = "Journal Entries"
        indexes = [
            models.Index(fields=['account', 'debit', 'credit']),
            models.Index(fields=['voucher', 'account']),
            models.Index(fields=['ref_number']),
        ]
    
    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("A single entry line cannot have both a debit and a credit.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Entry must have either a debit or a credit.")

    def __str__(self):
        return f"{self.account.name}: {self.debit if self.debit > 0 else self.credit}"

class DayBook(BusinessOwnedModel):
    """
    GOD-MODE: Persistent Day Book record.
    Links transactions directly to documents for strict traceability.
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True)
    voucher = models.OneToOneField(Voucher, on_delete=models.CASCADE, related_name='day_book_entry')
    date = models.DateField()
    particulars = models.TextField(help_text="Flattened summary like 'Dr Bank To Sales'")
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)

    def __str__(self):
        return f"DayBook | {self.date} | {self.amount}"

class TrialBalanceSnapshot(BusinessOwnedModel):
    """
    Captures the state of the Trial Balance at a specific point in time (usually after doc processing).
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    total_debit = models.DecimalField(max_digits=20, decimal_places=2)
    total_credit = models.DecimalField(max_digits=20, decimal_places=2)
    is_balanced = models.BooleanField(default=True)
    data_snapshot = models.JSONField(help_text="JSON dump of account balances")

class ProfitAndLossSnapshot(BusinessOwnedModel):
    """
    Captures the P&L state.
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    net_profit = models.DecimalField(max_digits=20, decimal_places=2)
    income_json = models.JSONField()
    expense_json = models.JSONField()


class AmortizationSchedule(BusinessOwnedModel):
    """
    ASC 606 & Matching Principle Engine.
    Spreads a single payment over multiple periods.
    """
    voucher = models.OneToOneField(Voucher, on_delete=models.CASCADE, related_name='amortization_schedule')
    asset_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='prepaid_schedules', help_text="e.g. Prepaid Insurance")
    expense_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='expense_schedules', help_text="e.g. Insurance Expense")
    
    total_amount = models.DecimalField(max_digits=20, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    periods = models.PositiveIntegerField(help_text="Number of months")
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Amortization: {self.expense_account.name} ({self.periods} months)"


class AmortizationMovement(models.Model):
    """
    Tracks each monthly journal entry created by the engine.
    """
    schedule = models.ForeignKey(AmortizationSchedule, on_delete=models.CASCADE, related_name='movements')
    journal_voucher = models.OneToOneField(Voucher, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    is_posted = models.BooleanField(default=False)
