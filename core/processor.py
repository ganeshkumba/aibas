import re
from datetime import datetime
from decimal import Decimal
from .models import Document, ExtractedLineItem, Business
from apps.ai_bridge.services.ai_service import AIService
import pytesseract

# AIService will be instantiated inside processing functions to avoid import-time side effects
# ---------- LEDGER KEYWORDS ----------
LEDGER_MAP = {
    'rent': 'Rent Expense',
    'salary': 'Salary Expense',
    'office': 'Office Expense',
    'sale': 'Sales Revenue',
    'purchase': 'Purchases',
    'bank': 'Bank',
}

GST_TYPES = ['CGST', 'SGST', 'IGST']

def classify_ledger(vendor_or_description):
    text = vendor_or_description.lower() if vendor_or_description else ''
    for keyword, ledger in LEDGER_MAP.items():
        if keyword in text:
            return ledger
    return 'Uncategorized'

def extract_gst(text):
    """Try to extract GST rate and tax amount from a line"""
    gst_rate = None
    tax_amount = None

    # Flexible GST pattern: e.g., CGST 5%, SGST 5%, IGST 12%
    rate_match = re.search(r'(\d{1,2})\s*%', text)
    if rate_match:
        gst_rate = rate_match.group(1) + '%'

    # Amount patterns: "Amount 123.45", "Total: 123.45"
    amount_match = re.search(r'(?:Amount|Total|Tax|Rs\.?)[:\s]+(\d+\.\d{2})', text, re.IGNORECASE)
    if amount_match:
        tax_amount = Decimal(amount_match.group(1))

    return gst_rate, tax_amount

def process_document(doc: Document):
    text = doc.ocr_text or ""

    # ---------- DEBUG: Show OCR ----------
    print(f"\n=== OCR TEXT FOR DOCUMENT {doc.id} ({doc.doc_type}) ===")
    print(text[:500] + "...") # Truncate for log
    print("=== END OCR TEXT ===\n")

    # ---------- AI STEP ----------
    ai_service = AIService()
    ai_data = {}
    try:
        ai_data = ai_service.process_document(text, doc_type=doc.doc_type)
        print(f"AI Data Received (Keys): {list(ai_data.keys())}")
        print(f"FULL AI DATA: {ai_data}")  # DEBUG: See complete AI response
        
        # Populate Document fields if AI found them
        if ai_data.get('invoice_no'):
            doc.document_number = ai_data['invoice_no']
        if ai_data.get('date'):
            try:
                doc.document_date = datetime.strptime(ai_data['date'], "%Y-%m-%d").date()
                print(f"Parsed document date: {doc.document_date}")
            except Exception as date_err:
                print(f"Date parsing error: {date_err}")
        doc.save()
    except Exception as e:
        print(f"AI Service Error: {e}")
        import traceback
        traceback.print_exc()
        ai_data = {"error": str(e)}

    # ---------- EXTRACTION LOGIC ----------
    items_created = 0

    if doc.doc_type == 'bank':
        # PROCESS BANK STATEMENT
        transactions = ai_data.get('transactions', [])
        print(f"Extracted {len(transactions)} bank transactions.")
        for tx in transactions:
            try:
                item = ExtractedLineItem(document=doc)
                item.date = datetime.strptime(tx['date'], "%Y-%m-%d").date() if tx.get('date') else None
                item.description = tx.get('description')
                
                amount = Decimal(str(tx.get('debit') or tx.get('credit') or 0))
                item.amount = amount
                
                if tx.get('debit'):
                    item.debit = Decimal(str(tx['debit']))
                    item.ledger_account = 'Bank Payment'
                elif tx.get('credit'):
                    item.credit = Decimal(str(tx['credit']))
                    item.ledger_account = 'Bank Receipt'
                
                item.invoice_no = tx.get('reference_no')
                item.balance = Decimal(str(tx.get('balance') or 0)) if tx.get('balance') else None
                
                if tx.get('type') == 'CHG':
                    item.ledger_account = 'Bank Charges'
                
                item.raw = tx
                item.save()
                items_created += 1
            except Exception as e:
                print(f"Failed to save bank transaction: {e}")

    else:
        # PROCESS INVOICE/RECEIPT (EXISTING LOGIC + ENHANCEMENTS)
        if ai_data.get('line_items'):
            for ai_item in ai_data['line_items']:
                try:
                    item = ExtractedLineItem(document=doc)
                    item.vendor = ai_data.get('vendor')
                    item.vendor_gstin = ai_data.get('vendor_gstin')
                    item.place_of_supply = ai_data.get('place_of_supply')
                    item.invoice_no = ai_data.get('invoice_no')
                    item.date = doc.document_date
                    item.amount = Decimal(str(ai_item.get('amount', 0)))
                    item.gst_rate = ai_item.get('tax_rate')
                    item.hsn_code = ai_item.get('hsn_code')
                    item.description = ai_item.get('description')
                    item.ledger_account = ai_item.get('ledger_suggestion') or classify_ledger(ai_item.get('description', ''))
                    
                    item.raw = {"source": "AI_LineItem", "ai_data": ai_item}
                    item.save()
                    items_created += 1
                except Exception as e:
                    print(f"Failed to save AI line item: {e}")

        # Fallback to Summary if no items
        if items_created == 0 and ai_data and "error" not in ai_data and ai_data.get("confidence", 0) > 30:
            try:
                item = ExtractedLineItem(document=doc)
                item.vendor = ai_data.get("vendor")
                item.vendor_gstin = ai_data.get('vendor_gstin')
                item.place_of_supply = ai_data.get('place_of_supply')
                item.invoice_no = ai_data.get("invoice_no")
                item.date = doc.document_date
                item.amount = Decimal(str(ai_data.get("total_amount") or 0))
                item.tax_amount = Decimal(str(ai_data.get("tax_amount") or 0))
                item.ledger_account = classify_ledger(ai_data.get("vendor"))
                item.raw = {"source": "AI_Summary", "ai_full_extraction": ai_data}
                item.save()
                items_created += 1
            except Exception as e:
                print(f"Failed to create AI summary line item: {e}")

    # ---------- LEDGER AUTOMATION (BRIDGE) ----------
    if items_created > 0:
        doc.status = "ocr_complete"  # Set status so automation service check passes
        doc.save()
        try:
            from apps.ledger.services.automation_service import AutomationService
            # Updated to handle potential multiple vouchers or specific bank logic
            AutomationService.convert_document_to_voucher(doc)
        except Exception as e:
            print(f"Ledger Automation Error: {e}")

    doc.status = "processed"
    doc.is_processed = True
    doc.save()
    print(f"Document {doc.id} processing complete. Items: {items_created}\n")


def generate_business_summary(business: Business):
    """
    Business Summary logic to show Income, Expense, and Profit.
    Uses the actual ledger entries for accuracy.
    """
    try:
        from apps.ledger.models import JournalEntry
        from django.db.models import Sum

        from apps.ledger.models import VoucherType
        pnl_vouchers = [VoucherType.SALES, VoucherType.PURCHASE, VoucherType.JOURNAL, VoucherType.CREDIT_NOTE, VoucherType.DEBIT_NOTE]
        
        income = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='INCOME',
            voucher__voucher_type__in=pnl_vouchers
        ).aggregate(total=Sum('credit') - Sum('debit'))['total'] or Decimal('0.00')

        expense = JournalEntry.objects.filter(
            account__business=business,
            account__group__classification='EXPENSE',
            voucher__voucher_type__in=pnl_vouchers
        ).aggregate(total=Sum('debit') - Sum('credit'))['total'] or Decimal('0.00')

        return {
            'total_income': income,
            'total_expense': expense,
            'net_profit': income - expense
        }
    except Exception:
        return {
            'total_income': Decimal('0.00'),
            'total_expense': Decimal('0.00'),
            'net_profit': Decimal('0.00')
        }