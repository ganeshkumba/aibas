import requests
import json
import re
from django.conf import settings
from .base import BaseAIProvider


class OllamaProvider(BaseAIProvider):
    def __init__(self, model=None):
        self.model = model or getattr(settings, 'OLLAMA_MODEL', "llama3.1")
        self.url = getattr(settings, 'OLLAMA_URL', "http://localhost:11434/api/generate")

    def extract(self, text: str, doc_type: str = 'receipt', context: dict = None) -> dict:
        # Truncate text to avoid choking CPU-based Ollama instances
        safe_text = (text or "")[:6000]
        context = context or {}
        biz_gstin = context.get('business_gstin', 'UNKNOWN')
        state_code = biz_gstin[:2] if biz_gstin != 'UNKNOWN' else 'XX'
        
        if doc_type == 'bank':
            prompt = f"""
SYSTEM: You are an Elite Indian Chartered Accountant specializing in Bank Reconciliation.
TASK: Extract all transaction rows from the bank statement text.

FORMAT: Return ONLY a valid JSON object.
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
      "balance": 0.0
    }}
  ],
  "accounting_logic": "Note any missing balances or unusual entries"
}}

RULES:
1. Debit (Dr) = Money going OUT (Payments).
2. Credit (Cr) = Money coming IN (Receipts).
3. If only one 'Amount' column exists, look for 'Dr/Cr' or 'Deposit/Withdrawal' indicators.

DOCUMENT TEXT:
{safe_text}
"""
        else:
            prompt = f"""
SYSTEM: You are an Expert Indian CA and Tax Consultant.
TASK: Extract structured data for Tally-compliant accounting.
MY BUSINESS GSTIN: {biz_gstin}

{{
  "vendor": "Clean Name (No 'M/s', No Addresses)",
  "vendor_gstin": "...",
  "place_of_supply": "State Name",
  "invoice_no": "...",
  "date": "YYYY-MM-DD",
  "total_amount": 0.0,
  "tax_amount": 0.0,
  "gst_type": "CGST_SGST or IGST or EXEMPT",
  "line_items": [
    {{
      "description": "...",
      "hsn_code": "...",
      "amount": 0.0,
      "tax_rate": "18%",
      "ledger_suggestion": "e.g. Office Rent, Software Expense, Fixed Assets"
    }}
  ],
  "confidence": 0-100,
  "is_msme": false,
  "udyam_number": "...",
  "is_b2b": false,
  "accounting_logic": "Explain tax and ledger selection reasoning"
}}

RULES:
1. is_b2b: Set to TRUE only if MY GSTIN ({biz_gstin}) is found in the 'Bill To' or 'Buyer' section.
2. gst_type: If Vendor GSTIN starts with {state_code}, use 'CGST_SGST'. Otherwise 'IGST'.
3. is_msme: Look for 'MSME' text or 'Udyam' numbers.
4. amount: Total for the line (Taxable + Tax).
5. LEDGER RULE: If item > 10,000 and durable (Laptop, Phone), suggest 'Fixed Assets'. Otherwise use 'Indirect Expenses'.

DOCUMENT TEXT:
{safe_text}
"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": 4096,
                "temperature": 0,
                "num_thread": 8, # Optimize for modern CPUs
                "num_predict": 1024 # Limit response length for speed
            },
            "keep_alive": "5m"
        }

        full_response = ""
        max_retries = 2
        print(f"[Ollama] Calling AI at {self.url} with model {self.model}...")
        
        for attempt in range(max_retries):
            try:
                # 20s connect, 1200s (20 min) read timeout for slow CPUs
                response = requests.post(self.url, json=payload, timeout=(20, 1200))
                response.raise_for_status()
                full_response = response.json().get("response", "")
                print(f"[Ollama] Received response (len: {len(full_response)})")
                break
            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    print(f"[Ollama] ERROR: Server timed out after {max_retries} attempts.")
                    return {
                        "error": "Ollama server timed out after multiple attempts. 20-minute window exceeded.",
                        "raw_response": "TIMEOUT_ERROR"
                    }
                print(f"[Ollama] Timeout on attempt {attempt+1}, retrying...")
                continue
            except requests.exceptions.ConnectionError:
                print(f"[Ollama] ERROR: Connection failed to {self.url}")
                return {
                    "error": f"Could not connect to Ollama at {self.url}. Ensure the service is running and the port is correct.",
                    "raw_response": "CONNECTION_ERROR"
                }
            except Exception as e:
                print(f"[Ollama] ERROR: Unexpected error: {e}")
                return {
                    "error": str(e),
                    "raw_response": "UNEXPECTED_ERROR"
                }

        # Intelligent JSON Extraction
        json_str = ""
        markdown_match = re.search(r'```(?:json)?\s*(.*?)\s*```', full_response, re.DOTALL)
        if markdown_match:
            json_str = markdown_match.group(1)
        else:
            brace_match = re.search(r'(\{.*\})', full_response, re.DOTALL)
            if brace_match:
                json_str = brace_match.group(1)
            else:
                json_str = full_response

        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return {"error": "AI returned non-object JSON", "raw_response": full_response}
            return data
        except json.JSONDecodeError:
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(json_str[start:end+1])
                except: pass
            
            return {
                "error": "JSON Decode Error: Malformed AI response.",
                "raw_response": full_response
            }