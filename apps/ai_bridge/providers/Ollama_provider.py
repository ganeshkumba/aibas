import requests
import json
from django.conf import settings
from .base import BaseAIProvider


class OllamaProvider(BaseAIProvider):
    def __init__(self, model="llama3.1"):
        self.model = model
        self.url = getattr(settings, 'OLLAMA_URL', "http://localhost:11434/api/generate")

    def extract(self, text: str, doc_type: str = 'receipt') -> dict:
        if doc_type == 'bank':
            prompt = f"""
You are an expert Indian Chartered Accountant AI.
Extract all transactions from this bank statement text.

Return STRICT JSON only:
{{
  "account_number": "",
  "bank_name": "",
  "transactions": [
    {{
      "date": "YYYY-MM-DD",
      "description": "",
      "reference_no": "UTR or Cheque No",
      "debit": 0.0,
      "credit": 0.0,
      "balance": 0.0,
      "type": "PAYMENT/RECEIPT/CONTRA/CHG" 
    }}
  ],
  "confidence": 0-100
}}

DOCUMENT TEXT:
{text}
"""
        else:
            prompt = f"""
You are an expert Indian Chartered Accountant AI.

Extract structured data from the document text below.

Return STRICT JSON only:
{{
  "vendor": "",
  "vendor_gstin": "",
  "place_of_supply": "State Name",
  "invoice_no": "",
  "date": "YYYY-MM-DD",
  "total_amount": 0.0,
  "tax_amount": 0.0,
  "line_items": [
    {{
      "description": "",
      "hsn_code": "",
      "amount": 0.0,
      "tax_rate": "percentage",
      "ledger_suggestion": ""
    }}
  ],
  "confidence": 0-100
}}

DOCUMENT TEXT:
{text}
"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }   

        try:
            response = requests.post(self.url, json=payload, timeout=120)
            response.raise_for_status()
            raw = response.json()["response"]
            
            # Find the JSON block in case there's extra text
            import re
            json_match = re.search(r'(\{.*\})', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(1)

            return json.loads(raw)
        except Exception as e:
            return {
                "error": str(e),
                "raw_response": locals().get('raw', 'No response')
            }
