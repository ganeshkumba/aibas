import logging
import datetime
from decimal import Decimal
from django.db import transaction
from apps.inventory.models import Product, StockMovement, Batch, Category
from core.models import Document, ExtractedLineItem

logger = logging.getLogger(__name__)

class InventoryAutomationService:
    """
    God-Mode Inventory Service.
    Bridge between AI-extracted lines and the Virtual Warehouse.
    """

    @classmethod
    @transaction.atomic
    def update_stock_from_document(cls, document: Document):
        """
        Processes a document and updates inventory levels.
        """
        if document.doc_type != 'receipt':
            return
            
        # Determine if it's a Purchase (Stock IN) or Sale (Stock OUT)
        # We reuse the logic from AutomationService or check the result voucher
        # For simplicity, if it has a Purchase voucher linked, it's a Stock IN
        from apps.ledger.models import VoucherType
        
        vouchers = document.vouchers.all()
        if not vouchers.exists():
            logger.warning(f"No vouchers found for Doc {document.id}. Inventory update skipped.")
            return

        is_purchase = any(v.voucher_type == VoucherType.PURCHASE for v in vouchers)
        is_sales = any(v.voucher_type == VoucherType.SALES for v in vouchers)
        
        if not (is_purchase or is_sales):
            return

        move_type = 'IN' if is_purchase else 'OUT'
        lines = document.lines.all()
        
        for line in lines:
            if not line.description or not line.amount:
                continue
                
            # 1. Resolve Product (Fuzzy match on description)
            product_name = line.description.strip()
            product = Product.objects.filter(business=document.business, name__iexact=product_name).first()
            
            if not product:
                # Automtically create the product if missing
                # This is the 'Zero Setup' philosophy
                product = Product.objects.create(
                    business=document.business,
                    name=product_name,
                    sku=line.hsn_code,
                    hsn_code=line.hsn_code,
                    default_purchase_price=line.amount if is_purchase else 0,
                    default_sales_price=line.amount if is_sales else 0,
                    tax_rate=Decimal(str(line.gst_rate or '0').replace('%', '') or '0')
                )
                logger.info(f"AI Audit: New product created - {product.name}")

            # 2. Batch/Expiry God-Mode (Extract from raw JSON if available)
            batch = None
            raw_data = line.raw or {}
            batch_no = raw_data.get('batch_no') or raw_data.get('batch')
            expiry = raw_data.get('expiry') or raw_data.get('exp_date')
            
            if batch_no:
                batch, _ = Batch.objects.get_or_create(
                    business=document.business,
                    product=product,
                    batch_number=batch_no,
                    defaults={'expiry_date': cls._parse_date(expiry)}
                )

            # 3. Record Movement
            # AI Hack: If quantity is missing, we assume 1 or try to derive from amount
            qty = Decimal(str(raw_data.get('quantity') or 1))
            
            StockMovement.objects.create(
                business=document.business,
                product=product,
                batch=batch,
                type=move_type,
                quantity=qty,
                unit_price=line.amount / qty if qty > 0 else line.amount,
                document=document,
                extracted_line=line,
                date=document.document_date or datetime.date.today(),
                remarks=f"AI Auto-Ingest from {document.document_number}"
            )
            logger.info(f"Stock {move_type}: {qty} {product.name} recorded.")

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        try:
            # Add complex date parsing if needed
            return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            return None
