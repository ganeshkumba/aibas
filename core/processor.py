import os
import re
import logging
import threading
from datetime import datetime
from decimal import Decimal

import pytesseract
import pdfplumber
from django.conf import settings
from django.db import transaction

from .models import Document, ExtractedLineItem, Business
from apps.ai_bridge.services.ai_service import AIService
from apps.ledger.services.automation_service import AutomationService

logger = logging.getLogger(__name__)

# --- PERFORMANCE GUARDRAILS ---
AI_CONCURRENCY_LIMIT = 2 # Max simultaneous AI requests
ai_semaphore = threading.Semaphore(AI_CONCURRENCY_LIMIT)

# --- OCR System Setup ---
def setup_ocr():
    tess_path = getattr(settings, 'TESSERACT_CMD', None)
    if tess_path and os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
    elif os.name == 'nt':
        # Legacy fallback if not in settings but exists in default path
        default_nt = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(default_nt):
            pytesseract.pytesseract.tesseract_cmd = default_nt

setup_ocr()

class DocumentProcessor:
    """
    Elite Orchestrator for Document Intelligence.
    Handles OCR pipeline, AI Extraction, and Ledger Bridging.
    """
    
    def __init__(self, document_id):
        try:
            self.document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            self.document = None
            logger.error(f"Document {document_id} not found.")

    def run(self):
        """Main execution flow"""
        if not self.document:
            return

        try:
            # 1. OCR Stage
            if not self.document.ocr_text:
                self._perform_ocr()
            
            # If using Gemini, we don't strictly need local OCR text as it has Vision
            is_gemini = getattr(settings, 'AI_PROVIDER', '').lower() == 'gemini'
            if not self.document.ocr_text.strip() and not is_gemini:
                self._fail("OCR_PROCESS", "No legible text found in document.")
                return

            # 2. AI Stage (With Concurrency Control)
            logger.info(f"Doc {self.document.id}: Waiting for AI slot...")
            with ai_semaphore:
                logger.info(f"Doc {self.document.id}: Entering AI Extraction stage.")
                ai_data = self._extract_ai_data()
            
            if not ai_data or "error" in ai_data:
                err_msg = ai_data.get("error", "AI Extraction returned empty results")
                self._fail("AI_EXTRACTION", err_msg, raw=ai_data.get("raw_response"))
                return

            # 3. Persistence Stage
            self._save_extracted_data(ai_data)

            # 4. Automation Stage
            self._bridge_to_ledger()

            # 5. Finalize
            self._success()

        except Exception as e:
            logger.exception(f"Critical failure in processor for doc {self.document.id}")
            self._fail("CRITICAL_SYSTEM_ERROR", str(e))

    def _perform_ocr(self):
        """Extracts text from PDF or Images with Scanned PDF Fallback"""
        filepath = self.document.file.path
        text = ""
        # Speed tweak: OEM 1 (Neural) vs 3 (Default). 
        # Using PSM 3 (Auto) with standard Indian fonts
        tess_config = "--oem 1 --psm 3"
        
        try:
            from PIL import Image, ImageOps
            if filepath.lower().endswith('.pdf'):
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted and len(extracted.strip()) > 10:
                            text += extracted + "\n"
                        else:
                            # FALLBACK: Scanned PDF page
                            try:
                                logger.info(f"Scanned page in {self.document.id}, initializing fast OCR.")
                                # Optimization: 200 DPI is usually enough for Tesseract and much faster than 300
                                img = page.to_image(resolution=200).original
                                text += pytesseract.image_to_string(img, config=tess_config) + "\n"
                            except Exception as ocr_err:
                                logger.warning(f"Failed to OCR scanned page: {ocr_err}")
            else:
                # Image file: applying basic preprocessing for accuracy
                img = Image.open(filepath)
                img = ImageOps.grayscale(img)
                # Auto-orient
                try:
                    img = ImageOps.exif_transpose(img)
                except: pass
                text = pytesseract.image_to_string(img, config=tess_config)
            
            self.document.ocr_text = text
            self.document.save()
        except Exception as e:
            logger.error(f"OCR Error for {self.document.id}: {e}")
            raise

    def _extract_ai_data(self):
        """Calls AIService for structured parsing"""
        ai_service = AIService()
        context = {
            'business_gstin': self.document.business.gstin,
            'file_path': self.document.file.path
        }
        return ai_service.process_document(
            self.document.ocr_text, 
            doc_type=self.document.doc_type,
            context=context
        )

    def _save_extracted_data(self, ai_data):
        """Maps AI JSON to ExtractedLineItem models"""
        # Update Document Header
        if ai_data.get('invoice_no'):
            self.document.document_number = ai_data['invoice_no']
        
        if ai_data.get('date'):
            self.document.document_date = self._parse_date(ai_data['date'])
        
        if ai_data.get('confidence'):
            try:
                self.document.confidence = float(ai_data['confidence'])
            except:
                pass
        
        # --- God Level Persistence ---
        self.document.is_msme = ai_data.get('is_msme', False)
        self.document.udyam_number = ai_data.get('udyam_number')
        self.document.is_b2b = ai_data.get('is_b2b', False)
        self.document.accounting_logic = ai_data.get('accounting_logic')

        # Rule A: MSME 45-Day Trap (Section 43B(h))
        if self.document.is_msme and self.document.document_date:
            from datetime import timedelta
            self.document.payment_deadline = self.document.document_date + timedelta(days=45)
        
        # Point: Advanced Vision Transcription Support
        # If Gemini (Vision) improved the text, save it so the CA can audit it later.
        if ai_data.get('transcribed_text'):
            self.document.ocr_text = ai_data['transcribed_text']

        self.document.save()

        # Create Line Items
        with transaction.atomic():
            # Clear old items if reprocessing
            self.document.lines.all().delete()
            self.document.vouchers.all().delete()
            
            if self.document.doc_type == 'bank':
                self._process_bank_transactions(ai_data.get('transactions', []))
            else:
                self._process_invoice_lines(ai_data)

    def _process_bank_transactions(self, transactions):
        for tx in transactions:
            item = ExtractedLineItem(document=self.document)
            item.date = self._parse_date(tx.get('date'))
            item.vendor = tx.get('description')
            
            # Extract amount safely
            debit = Decimal(str(tx.get('debit') or 0))
            credit = Decimal(str(tx.get('credit') or 0))
            item.amount = debit if debit > 0 else credit
            item.debit = debit
            item.credit = credit
            
            # Smart Defaulting for Bank Statements
            item.ledger_account = 'Pending Classification'
            
            item.invoice_no = tx.get('reference_no')
            item.raw = tx
            item.save()

    def _process_invoice_lines(self, ai_data):
        vendor = ai_data.get('vendor')
        vendor_gstin = ai_data.get('vendor_gstin')
        invoice_no = ai_data.get('invoice_no')
        
        for li in ai_data.get('line_items', []):
            item = ExtractedLineItem(document=self.document)
            item.vendor = vendor
            item.vendor_gstin = vendor_gstin
            item.invoice_no = invoice_no
            item.date = self.document.document_date
            item.amount = Decimal(str(li.get('amount', 0)))
            item.gst_rate = li.get('tax_rate')
            item.description = li.get('description')
            item.hsn_code = li.get('hsn_code')
            item.ledger_account = li.get('ledger_suggestion') or "Uncategorized"
            item.raw = li
            item.save()

    def _bridge_to_ledger(self):
        """Converts extracted lines to double-entry vouchers"""
        self.document.status = "ocr_complete"
        self.document.save()
        try:
            AutomationService.convert_document_to_voucher(self.document)
        except Exception as e:
            logger.error(f"Automation Bridge Failed: {e}")
            raise

    def _parse_date(self, date_str):
        if not date_str: return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue
        return None

    def _fail(self, step, message, raw=None):
        self.document.status = "failed"
        self.document.extraction_errors = {
            "step": step,
            "message": message,
            "raw": raw
        }
        self.document.save()

    def _success(self):
        self.document.status = "processed"
        self.document.is_processed = True
        self.document.extraction_errors = {}
        self.document.save()

def process_document(doc_id):
    """Entry point for threading"""
    processor = DocumentProcessor(doc_id)
    processor.run()