import google.generativeai as genai
import json
import logging
import os
import mimetypes
from django.conf import settings
from .base import BaseAIProvider
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# --- CFO-GRADE SCHEMAS (Validated) ---

class LineItemSchema(BaseModel):
    description: str = Field(..., description="Product/Service description")
    amount: float = Field(..., description="Total for this line item (Taxable + Tax)")
    tax_rate: str = Field("18%", pattern=r"^\d+%$")
    hsn_code: Optional[str] = None
    ledger_suggestion: str = Field(..., description="Tally Ledger mapping")
    
    @field_validator('amount')
    @classmethod
    def round_amount(cls, v): return round(v, 2)

class InvoiceSchema(BaseModel):
    vendor: str = Field(..., description="Professional entity name (No addresses, No 'M/s')")
    vendor_gstin: Optional[str] = None
    place_of_supply: Optional[str] = None
    invoice_no: str
    date: str = Field(..., pattern=r"\d{4}-\d{2}-\d{2}")
    total_amount: float
    tax_amount: float
    gst_type: str = Field(..., pattern="^(CGST_SGST|IGST|EXEMPT)$")
    line_items: List[LineItemSchema]
    confidence: float
    transcribed_text: Optional[str] = Field(None, description="Full raw text transcription")
    accounting_logic: str = Field(..., description="Explain the reasoning for tax and ledger choices")
    
    # --- God Level Fields ---
    is_msme: bool = Field(False, description="True if 'MSME' logo or 'Udyam' number is found")
    udyam_number: Optional[str] = Field(None, description="Extracted Udyam Registration Number")
    is_b2b: bool = Field(False, description="True if my company GSTIN is listed in the 'Bill To' section")

class BankTransactionSchema(BaseModel):
    date: str
    description: str
    reference_no: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    balance: float = 0.0
    category: Optional[str] = None
    purpose: Optional[str] = None

class BankStatementSchema(BaseModel):
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    transactions: List[BankTransactionSchema]
    accounting_logic: str = Field(..., description="Note any missing balances or unusual entries")

class GeminiProvider(BaseAIProvider):
    def __init__(self):
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured in settings.")
        
        genai.configure(api_key=api_key)
        
        # Virtual CFO Persona
        system_instruction = (
            "You are a Senior Audit Partner. You process documents using VISUAL SPATIAL REASONING. "
            "1. IMAGE ANALYSIS: Read text, logos, stamps, and handwritten notes. "
            "2. MATH GUARD: Ensure line item sums match the total. "
            "3. CLEANING: Remove 'M/s', 'Private Limited', and city names from 'vendor' name. "
            "4. VOUCHER LOCK: Never suggest 'Income' for Purchases. Items > ₹10,000 are usually Fixed Assets. "
            "5. MSME DETECTION: Look for 'MSME' text, logos, or 'Udyam' registration numbers. "
            "6. BILL-TO CHECK: Verify if the provided 'MY GSTIN' is written in the 'Bill To' or 'Customer' section."
        )
        
        self.model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            system_instruction=system_instruction
        )

    def extract(self, text: str, doc_type: str = 'receipt', context: Dict = None) -> Dict[str, Any]:
        context = context or {}
        business_gstin = context.get('business_gstin', 'UNKNOWN')
        file_path = context.get('file_path')
        ledger_whitelist = context.get('allowed_ledgers', [])

        if doc_type == 'bank':
            prompt = self._get_bank_prompt(text)
        else:
            prompt = self._get_receipt_prompt(text, business_gstin, ledger_whitelist)

        try:
            # MULTIMODAL payload
            payload = [prompt]
            has_file = False
            if file_path and os.path.exists(file_path):
                mime_type, _ = mimetypes.guess_type(file_path)
                try:
                    with open(file_path, "rb") as f:
                        payload.append({
                            "mime_type": mime_type or "image/jpeg",
                            "data": f.read()
                        })
                        has_file = True
                except Exception as e:
                    logger.warning(f"[Gemini] Could not read file {file_path}: {e}. Falling back to text.")
            
            if not has_file:
                payload.append(text)

            try:
                response = self.model.generate_content(
                    payload,
                    generation_config={"response_mime_type": "application/json", "temperature": 0}
                )
            except Exception as multimodal_err:
                if has_file and text and text.strip():
                    logger.warning(f"[Gemini] Multimodal failed: {multimodal_err}. Retrying with text-only.")
                    # Fallback to Text-only if multimodal fails (e.g. corrupt PDF)
                    response = self.model.generate_content(
                        [prompt, text],
                        generation_config={"response_mime_type": "application/json", "temperature": 0}
                    )
                else:
                    raise multimodal_err
            
            raw_data = json.loads(response.text)

            # Pydantic Enforcement
            if doc_type == 'bank':
                validated = BankStatementSchema(**raw_data)
            else:
                validated = InvoiceSchema(**raw_data)
                
            return validated.model_dump()

        except ValidationError as ve:
            logger.error(f"[Gemini] Audit Failed: {ve.json()}")
            return {"error": "Validation Failed", "details": ve.errors()}
        except Exception as e:
            logger.error(f"[Gemini Provider] Critical Error: {e}")
            return {"error": str(e)}

    def _get_bank_prompt(self, text: str) -> str:
        return f"""
TASK: Extract bank transactions into structured registry. 
Ensure you identify the PURPOSE of the transaction (e.g., Bank Charges, Interest, GST Payment, Vendor Payment, Customer Receipt).

JSON STRUCTURE:
{{
  "account_number": "...",
  "bank_name": "...",
  "transactions": [
    {{ 
      "date": "YYYY-MM-DD", 
      "description": "...", 
      "reference_no": "...", 
      "debit": 0.0, 
      "credit": 0.0, 
      "balance": 0.0,
      "category": "e.g. Bank Charges, Interest Income, Professional Fees, Sales Receipt",
      "purpose": "Briefly explain what this transaction is for"
    }}
  ],
  "accounting_logic": "Explain any reconciliation notes here"
}}
"""

    def _get_receipt_prompt(self, text: str, business_gstin: str, whitelist: List[str]) -> str:
        state_code = business_gstin[:2] if business_gstin else "UNKNOWN"
        return f"""
Audit-level Tax Invoice extraction.
MY GSTIN: {business_gstin} (State: {state_code})
ALLOWED LEDGERS: {whitelist}

LOGIC:
- If Vendor GSTIN starts with {state_code} -> gst_type: "CGST_SGST".
- Else -> gst_type: "IGST".
- If item cost > 10,000 and is durable (e.g. Furniture, Laptop), suggest Asset ledgers.
- Explain math and ledger selection in 'accounting_logic'.

JSON STRUCTURE:
{{
  "vendor": "Clean Name",
  "vendor_gstin": "...",
  "place_of_supply": "...",
  "invoice_no": "...",
  "date": "YYYY-MM-DD",
  "total_amount": 0.0,
  "tax_amount": 0.0,
  "gst_type": "CGST_SGST/IGST/EXEMPT",
  "line_items": [
    {{ "description": "...", "hsn_code": "...", "amount": 0.0, "tax_rate": "18%", "ledger_suggestion": "..." }}
  ],
  "confidence": 0.0,
  "transcribed_text": "...",
  "accounting_logic": "...",
  "is_msme": false,
  "udyam_number": "...",
  "is_b2b": false
}}
"""