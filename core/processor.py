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
    print(f"\n=== OCR TEXT FOR DOCUMENT {doc.id} ===")
    print(text)
    print("=== END OCR TEXT ===\n")

    # ---------- AI STEP ----------
    ai_service = AIService()
    ai_data = {}
    try:
        ai_data = ai_service.process_document(text)
        print(f"AI Data: {ai_data}")
        
        # Populate Document fields if AI found them
        if ai_data.get('invoice_no'):
            doc.document_number = ai_data['invoice_no']
        if ai_data.get('date'):
            try:
                # Expecting YYYY-MM-DD from AI
                doc.document_date = datetime.strptime(ai_data['date'], "%Y-%m-%d").date()
            except:
                pass
        doc.save()
    except Exception as e:
        print(f"AI Service Error: {e}")
        ai_data = {"error": str(e)}

    # ---------- EXTRACTION LOGIC ----------
    items_created = 0

    # 1. Try AI Line Items
    if ai_data.get('line_items'):
        print(f"Using AI for line item extraction...")
        for ai_item in ai_data['line_items']:
            try:
                item = ExtractedLineItem(document=doc)
                item.vendor = ai_data.get('vendor')
                item.invoice_no = ai_data.get('invoice_no')
                item.date = doc.document_date
                item.amount = Decimal(str(ai_item.get('amount', 0)))
                # Extract tax rate if present
                item.gst_rate = ai_item.get('tax_rate')
                item.ledger_account = ai_item.get('ledger_suggestion') or classify_ledger(ai_item.get('description', ''))
                
                item.raw = {"source": "AI_LineItem", "ai_data": ai_item}
                item.save()
                items_created += 1
            except Exception as e:
                print(f"Failed to save AI line item: {e}")

    # 2. If no line items, try AI Summary Header
    if items_created == 0 and ai_data and "error" not in ai_data and ai_data.get("confidence", 0) > 40:
        if ai_data.get('total_amount') or ai_data.get('vendor'):
            try:
                item = ExtractedLineItem(document=doc)
                item.vendor = ai_data.get("vendor")
                item.invoice_no = ai_data.get("invoice_no")
                item.date = doc.document_date
                item.amount = Decimal(str(ai_data.get("total_amount") or 0))
                item.tax_amount = Decimal(str(ai_data.get("tax_amount") or 0))
                item.ledger_account = classify_ledger(ai_data.get("vendor"))
                item.raw = {"source": "AI_Summary", "ai_full_extraction": ai_data}
                item.save()
                items_created += 1
                print(f"Created AI summary line item: {item}")
            except Exception as e:
                print(f"Failed to create AI summary line item: {e}")

    # 3. Fallback to Regex if still no items
    if items_created == 0:
        print("Falling back to Regex line-by-line extraction...")
        lines = text.split("\n")
        for raw_line in lines:
            line = raw_line.strip()
            if not line or len(line) < 5:
                continue

            amount_match = re.findall(r'\d+\.\d{2}', line)
            date_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', line)
            
            if amount_match or date_match:
                try:
                    item = ExtractedLineItem(document=doc)
                    if date_match:
                        try:
                            item.date = datetime.strptime(date_match.group(1).replace('-', '/'), "%d/%m/%Y").date()
                        except: pass
                    
                    if amount_match:
                        item.amount = Decimal(amount_match[-1])
                    
                    # Try to find a vendor or invoice on this same line
                    vendor_match = re.search(r'(?:Vendor|From)[:\s]*([A-Za-z0-9 &]+)', line, re.IGNORECASE)
                    item.vendor = vendor_match.group(1) if vendor_match else None
                    item.ledger_account = classify_ledger(item.vendor or line)
                    
                    gst_rate, tax_amount = extract_gst(line)
                    item.gst_rate = gst_rate
                    item.tax_amount = tax_amount
                    
                    item.raw = {"source": "Regex_Fallback", "line": line}
                    item.save()
                    items_created += 1
                except Exception as e:
                    print(f"Failed to save regex fallback line: {e}")

    # ---------- LEDGER AUTOMATION (BRIDGE) ----------
    if items_created > 0:
        try:
            from apps.ledger.services.automation_service import AutomationService
            voucher = AutomationService.convert_document_to_voucher(doc)
            if voucher:
                print(f"Created draft ledger voucher: {voucher.voucher_number}")
        except Exception as e:
            print(f"Ledger Automation Error: {e}")

    doc.status = "processed"
    doc.save()
    print(f"Document {doc.id} processing complete. Items: {items_created}\n")


def generate_business_summary(business: Business):
    ledger_totals = {}
    gst_totals = {}
    total_income = Decimal('0')
    total_expense = Decimal('0')

    for doc in business.documents.all():
        for line in doc.lines.all():
            ledger = line.ledger_account or 'Uncategorized'
            ledger_totals[ledger] = ledger_totals.get(ledger, Decimal('0')) + (line.amount or 0)
            gst_rate = line.gst_rate or 'No GST'
            gst_totals[gst_rate] = gst_totals.get(gst_rate, Decimal('0')) + (line.tax_amount or 0)
            if 'Revenue' in ledger:
                total_income += line.amount or 0
            else:
                total_expense += line.amount or 0

    net_profit = total_income - total_expense

    return {
        'ledger_totals': ledger_totals,
        'gst_totals': gst_totals,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_profit': net_profit
    }