from .base import BaseAIProvider


class MockAIProvider(BaseAIProvider):
    """
    Simple, deterministic mock provider that returns hard‑coded,
    but realistic looking invoice data from raw text.
    Used for local testing without calling a real LLM.
    """

    def extract(self, text: str) -> dict:
        # Simulated extraction output
        return {
            "vendor": "Generic Supplier Ltd",
            "invoice_no": "MOCK-INV-001",
            "date": "2026-01-04",
            "total_amount": 1180.00,
            "tax_amount": 180.00,
            "line_items": [
                {
                    "description": "Consulting Services",
                    "amount": 1000.00,
                    "tax_rate": "18%",
                    "ledger_suggestion": "Consulting Fees"
                },
                {
                    "description": "GST (18%)",
                    "amount": 180.00,
                    "tax_rate": "18%",
                    "ledger_suggestion": "IGST"
                }
            ],
            "confidence": 90,
        }
