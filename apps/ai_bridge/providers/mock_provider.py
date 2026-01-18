from .base import BaseAIProvider


class MockAIProvider(BaseAIProvider):
    """
    Simple, deterministic mock provider that returns hard‑coded,
    but realistic looking invoice data from raw text.
    Used for local testing without calling a real LLM.
    """

    def extract(self, text: str, doc_type: str = 'receipt') -> dict:
        text_upper = text.upper()
        if doc_type == 'bank':
            # ... (keep bank data as is, but maybe add text matching later)
            return {
                "account_number": "50100234567890",
                "bank_name": "HDFC Bank",
                "transactions": [
                    { "date": "2023-10-05", "description": "NEFT-AWS Cloud Services", "reference_no": "N287230001", "debit": 10030.00, "credit": 0, "balance": 334120.25, "type": "PAYMENT" },
                    { "date": "2023-10-12", "description": "CHQ-Office Depot Supplies", "reference_no": "123456", "debit": 5900.00, "credit": 0, "balance": 328220.25, "type": "PAYMENT" },
                    { "date": "2023-10-15", "description": "NEFT CR-RECONCILIATION PREV INVOICE", "reference_no": "N287230045", "debit": 0, "credit": 106200.00, "balance": 434420.25, "type": "RECEIPT" },
                    { "date": "2023-10-18", "description": "Bank Charges - Consolidated", "reference_no": "-", "debit": 50.00, "credit": 0, "balance": 434370.25, "type": "CHG" },
                    { "date": "2023-10-20", "description": "UPI-Fast Track Couriers", "reference_no": "FTC/23/1056", "debit": 1200.00, "credit": 0, "balance": 433170.25, "type": "PAYMENT" },
                    { "date": "2023-10-25", "description": "RTGS-Nexus Consulting", "reference_no": "R287230078", "debit": 59000.00, "credit": 0, "balance": 374170.25, "type": "PAYMENT" },
                    { "date": "2023-10-30", "description": "Interest Credit", "reference_no": "-", "debit": 0, "credit": 1205.00, "balance": 375375.25, "type": "RECEIPT" }
                ],
                "confidence": 95
            }
        
        # DYNAMIC MOCKING FOR RECEIPTS
        if "AWS" in text_upper:
            return {
                "vendor": "Amazon Web Services", "vendor_gstin": "29CCCCC2222C1Z2", "place_of_supply": "Karnataka",
                "invoice_no": "AWS-OCT23-12345", "date": "2023-10-05", "total_amount": 10030.00, "tax_amount": 1530.00,
                "line_items": [{"description": "Cloud Hosting Services", "hsn_code": "998314", "amount": 10030.00, "tax_rate": "18%", "ledger_suggestion": "AWS Cloud Expenses"}],
                "confidence": 98
            }
        elif "RENT" in text_upper or "REALTY" in text_upper:
            return {
                "vendor": "Reliable Realty", "vendor_gstin": None, "place_of_supply": "Maharashtra",
                "invoice_no": "RENT-OCT-23", "date": "2023-10-01", "total_amount": 25000.00, "tax_amount": 0,
                "line_items": [{"description": "Office Space Rent", "hsn_code": "997212", "amount": 25000.00, "tax_rate": "0%", "ledger_suggestion": "Office Rent"}],
                "confidence": 95
            }
        elif "PENS" in text_upper or "PAPER" in text_upper:
            return {
                "vendor": "Stationery World", "vendor_gstin": "27BBBBB1111B1Z2", "place_of_supply": "Maharashtra",
                "invoice_no": "SW/24/0056", "date": "2023-10-12", "total_amount": 5900.00, "tax_amount": 900.00,
                "line_items": [{"description": "Office Supplies", "hsn_code": "4802", "amount": 5000.00, "tax_rate": "18%", "ledger_suggestion": "Office Supplies"}],
                "confidence": 92
            }
        
        # Default fallback
        return {
            "vendor": "Generic Supplier Ltd", "vendor_gstin": "27AAAAA0000A1Z5", "place_of_supply": "Maharashtra",
            "invoice_no": "MOCK-INV-001", "date": "2023-10-10", "total_amount": 1180.00, "tax_amount": 180.00,
            "line_items": [{"description": "Consulting Services", "hsn_code": "998314", "amount": 1000.00, "tax_rate": "18%", "ledger_suggestion": "Consulting Fees"}],
            "confidence": 90
        }
