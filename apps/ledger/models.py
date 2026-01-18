from django.db import models
from django.core.exceptions import ValidationError
from core.models import Business, Document
import uuid

class FinancialYear(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='financial_years')
    start_date = models.DateField()
    end_date = models.DateField()
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name}: {self.start_date.year}-{self.end_date.year}"

class AccountGroup(models.Model):
    """
    Hierarchical groups for the Chart of Accounts.
    Example: Assets -> Current Assets -> Bank Accounts
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
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

class Account(models.Model):
    """
    The actual Ledger Account.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    group = models.ForeignKey(AccountGroup, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True) # Optional accounting code
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    
    # Fixed nature derived from group at creation
    classification = models.CharField(max_length=20, choices=AccountGroup.Classification.choices, default='ASSET')
    is_system_reserved = models.BooleanField(default=False)
    
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

class VoucherSeries(models.Model):
    """
    Defines numbering schemes for different voucher types.
    Example: Prefix='PUR/', Suffix='/23-24', StartNumber=1, Padding=3 -> PUR/001/23-24
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    voucher_type = models.CharField(max_length=20, choices=VoucherType.choices)
    prefix = models.CharField(max_length=20, blank=True)
    suffix = models.CharField(max_length=20, blank=True)
    current_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('business', 'voucher_type', 'prefix')

class Voucher(models.Model):
    """
    Header for a transaction.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True, related_name='vouchers')
    voucher_type = models.CharField(max_length=20, choices=VoucherType.choices)
    voucher_number = models.CharField(max_length=50) # Auto-generated per type/business
    date = models.DateField()
    narration = models.TextField(blank=True)
    
    # Added for Bank Statement & Tally logic
    utr_number = models.CharField(max_length=100, blank=True, null=True)
    cheque_number = models.CharField(max_length=50, blank=True, null=True)

    # Audit Trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_draft = models.BooleanField(default=True) # AI drafts start here
    
    # Forensic / Dedup properties
    fingerprint = models.CharField(max_length=255, unique=True, null=True, blank=True, 
                               help_text="hash(vendor + invoice_no + date + total_amount)")
    
    class Meta:
        unique_together = ('business', 'voucher_type', 'voucher_number', 'financial_year')

    @property
    def total_amount(self):
        from decimal import Decimal
        return sum(e.debit for e in self.entries.all()) or Decimal('0.00')

    def __str__(self):
        return f"{self.voucher_type} #{self.voucher_number} | {self.date}"

class JournalEntry(models.Model):
    """
    Double Entry line items.
    Sum of debits must equal sum of credits for a given Voucher.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    
    debit = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    
    # Added for Bill Wise Allocation (Tally)
    REF_TYPES = [
        ('NEW', 'New Ref'),
        ('AGST', 'Against Ref'),
        ('ADV', 'Advance'),
        ('ON_ACC', 'On Account'),
    ]
    ref_type = models.CharField(max_length=10, choices=REF_TYPES, blank=True, null=True)
    ref_number = models.CharField(max_length=100, blank=True, null=True)
    
    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("A single entry line cannot have both a debit and a credit.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Entry must have either a debit or a credit.")

    def __str__(self):
        return f"{self.account.name}: {self.debit if self.debit > 0 else self.credit}"
