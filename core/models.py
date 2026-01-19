from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator, FileExtensionValidator
from django.utils import timezone

# This helper gets the User model we defined in settings (apps.accounts.User)
User = get_user_model()


class Business(models.Model):
    """
    BUSINESS MODEL:
    Think of this as a 'Company Profile'. 
    It stores all the tax and identity info for a business that needs accounting.
    """
    
    # The official name of the company
    name = models.CharField(max_length=200)

    # PAN: Permanent Account Number (Unique ID for Tax in India)
    pan = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^[A-Z]{5}[0-9]{4}[A-Z]$', 'Invalid PAN format')]
    )

    # GSTIN: Goods and Services Tax Identification Number
    gstin = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        validators=[RegexValidator(
            r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$',
            'Invalid GSTIN format'
        )]
    )

    # The start and end dates of the financial year (e.g., April 1st to March 31st)
    financial_year_start = models.DateField(blank=True, null=True)
    financial_year_end = models.DateField(blank=True, null=True)

    # Who created this profile in the system (could be an accountant)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='businesses'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Status: Is the business currently active, or has it closed down?
    is_active = models.BooleanField(default=True)
    
    # Internal record for when the last draft report was made
    last_draft_generated_at = models.DateTimeField(blank=True, null=True)

    # The actual person who owns the company (the client)
    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='owned_businesses',
        help_text="Actual business owner / client"
    )

    # Added for Tally & Tax logic
    state = models.CharField(max_length=100, blank=True, null=True, help_text="Company's registered state (for GST POS logic)")
    address = models.TextField(blank=True, null=True)

    BUSINESS_STATUS = [
        ('onboarding', 'Onboarding'), # Just joined
        ('active', 'Active'),         # Normal operation
        ('paused', 'Paused'),         # Temporary stop
        ('closed', 'Closed'),         # Permanently shut
    ]
    status = models.CharField(
        max_length=20,
        choices=BUSINESS_STATUS,
        default='onboarding'
    )

    class Meta:
        ordering = ['-created_at'] # Shows newest businesses first
        indexes = [
            models.Index(fields=['created_by']),
            models.Index(fields=['owner']),
            models.Index(fields=['status']),
            models.Index(fields=['financial_year_start']),
        ]

    def __str__(self):
        return self.name


def upload_to(instance, filename):
    """
    Decides where to save files on the computer. 
    It organizes them by Business ID so folders don't get messy.
    """
    return f"business_{instance.business.id}/documents/{filename}"


class Document(models.Model):
    """
    DOCUMENT MODEL:
    Think of this as a 'Digital Filing Cabinet'.
    Every paper receipt or PDF invoice you upload is stored here.
    """
    DOC_TYPES = [
        ('receipt', 'Receipt/Invoice'),
        ('bank', 'Bank Statement'),
        ('other', 'Other'),
    ]

    # Which business does this receipt belong to?
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='documents'
    )
    
    # Who uploaded it?
    uploaded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )

    # The actual file (PDF/Image)
    file = models.FileField(
        upload_to=upload_to,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff']
        )]
    )

    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, default='receipt')
    
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('ocr_complete', 'OCR Complete'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='uploaded')

    # The 'Plain Text' that the AI reads from the image
    ocr_text = models.TextField(blank=True, null=True)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # The Invoice Number or Bill Number written on the paper
    document_number = models.CharField(
        max_length=100, blank=True, null=True, help_text="Invoice / reference number"
    )

    # The date written on the receipt
    document_date = models.DateField(blank=True, null=True)

    # Has the AI finished reading this?
    is_processed = models.BooleanField(default=False)
    
    # Advanced Tally Integration
    is_synced_to_tally = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    sync_log = models.TextField(blank=True, null=True)

    checksum = models.CharField(
        max_length=64, blank=True, null=True,
        help_text="Used to detect duplicate uploads"
    )

    extraction_errors = models.JSONField(default=dict, blank=True, help_text="List of issues found during AI processing")
    confidence = models.FloatField(default=0.0, help_text="AI Confidence Score (0-100)")

    # --- God-Level Indian Accounting Fields ---
    is_msme = models.BooleanField(default=False, help_text="Detected if Vendor is MSME registered")
    udyam_number = models.CharField(max_length=50, blank=True, null=True, help_text="Udyam Registration Number")
    payment_deadline = models.DateField(blank=True, null=True, help_text="Hard 45-day MSME deadline (Section 43B(h))")
    
    is_b2b = models.BooleanField(default=False, help_text="True if Business's GSTIN is present on the bill")
    accounting_logic = models.TextField(blank=True, null=True, help_text="AI's Chain-of-thought logic for audit trails")

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['business']),
            models.Index(fields=['uploaded_by']),
            models.Index(fields=['doc_type']),
            models.Index(fields=['document_number']),
        ]

    def __str__(self):
        return f"Document {self.id} - {self.business.name}"


class ExtractedLineItem(models.Model):
    """
    EXTRACTED LINE ITEM:
    Think of this as the 'AI's Notes'. 
    Once the AI reads a document, it writes down the specific details it found below.
    """
    # Link back to the original paper document
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='lines'
    )
    
    date = models.DateField(null=True, blank=True)
    
    # Who was paid? (e.g., "Amazon" or "Starbucks")
    vendor = models.CharField(max_length=255, blank=True, null=True)
    
    # Money details
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True) # Total price
    debit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True) # Taxes paid
    gst_rate = models.CharField(max_length=20, blank=True, null=True) # % of tax
    
    # Reference number
    invoice_no = models.CharField(max_length=200, blank=True, null=True)
    
    # Which "Category" this belongs to in the ledger (e.g., "Office Supplies")
    ledger_account = models.CharField(max_length=100, blank=True, null=True)
    
    # Added for Tally & Tax logic
    description = models.TextField(blank=True, null=True)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    place_of_supply = models.CharField(max_length=100, blank=True, null=True)
    vendor_gstin = models.CharField(max_length=20, blank=True, null=True)
    
    # --- God-Level TDS Logic ---
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0.0)
    tds_rate = models.CharField(max_length=10, blank=True, null=True, help_text="e.g. 10% or 2%")

    # A copy of the "Raw data" from the AI in case we need more details later
    raw = models.JSONField(default=dict, blank=True)

    # Has a human (accountant) checked if the AI was correct?
    is_verified = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['document']),
            models.Index(fields=['vendor']),
            models.Index(fields=['invoice_no']),
            models.Index(fields=['ledger_account']),
        ]

    def __str__(self):
        return f"Line {self.id} ({self.vendor or 'Unknown'} - {self.amount or 0})"

