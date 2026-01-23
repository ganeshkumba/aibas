from django.db import models
from core.models import Business, Document, ExtractedLineItem
from apps.ledger.models import Account

class Category(models.Model):
    name = models.CharField(max_length=100)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='inventory_categories')
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.business.name})"

class Product(models.Model):
    """
    Core product definition.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, null=True)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    uom = models.CharField(max_length=50, default='Units', help_text="Unit of Measure (e.g. Kg, Pcs, Box)")
    
    # Pricing
    default_purchase_price = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    default_sales_price = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    
    # GST Details
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="GST percentage")
    
    # Tracking
    track_inventory = models.BooleanField(default=True)
    track_batch = models.BooleanField(default=False)
    low_stock_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku or 'No SKU'})"

    @property
    def current_stock(self):
        incoming = StockMovement.objects.filter(product=self, type='IN').aggregate(models.Sum('quantity'))['quantity__sum'] or 0
        outgoing = StockMovement.objects.filter(product=self, type='OUT').aggregate(models.Sum('quantity'))['quantity__sum'] or 0
        return incoming - outgoing

class Batch(models.Model):
    """
    GOD-MODE: Automatic Batch & Expiry tracking extracted by AI.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
    manufacturing_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - Batch {self.batch_number}"

class StockMovement(models.Model):
    """
    Every time stock moves (Purchase, Sale, Adjustment).
    """
    TYPES = [
        ('IN', 'Incoming (Purchase/Return)'),
        ('OUT', 'Outgoing (Sale/Damage)'),
        ('ADJ', 'Adjustment'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    type = models.CharField(max_length=10, choices=TYPES)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    
    # Links to the documents and accounting entries
    document = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True)
    extracted_line = models.ForeignKey(ExtractedLineItem, on_delete=models.CASCADE, null=True, blank=True)
    
    date = models.DateField()
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} {self.quantity} {self.product.name} on {self.date}"
