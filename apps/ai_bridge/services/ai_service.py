import os
from django.conf import settings
from ..providers.mock_provider import MockAIProvider
from ..providers.Ollama_provider import OllamaProvider

class AIService:
    """
    Service layer to handle AI logic. 
    It delegates to a provider based on configuration.
    """

    def __init__(self):
        # In a real app, logic would check settings.py
        # For now, let's use an environment variable or default to mock
        provider_type = os.getenv('AI_PROVIDER', 'mock').lower()
        
        if provider_type == 'ollama':
            self.provider = OllamaProvider()
        else:
            self.provider = MockAIProvider()

    def process_document(self, text: str) -> dict:
        """
        Takes OCR text and returns structured data using the configured provider.
        """
        if not text.strip():
            return {
                "vendor": None,
                "invoice_no": None,
                "date": None,
                "amount": None,
                "gst_rate": None,
                "tax_amount": None,
                "confidence": 0.0
            }

        return self.provider.extract(text)
