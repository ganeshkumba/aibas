from django.conf import settings
from ..providers.Ollama_provider import OllamaProvider
from ..providers.Gemini_provider import GeminiProvider

class AIService:
    """
    Service layer to handle AI logic. 
    It delegates to a provider based on configuration.
    """

    def __init__(self):
        # Professional standard: use Django settings
        provider_type = getattr(settings, 'AI_PROVIDER', 'ollama').lower()
        
        if provider_type == 'gemini':
            self.provider = GeminiProvider()
        elif provider_type == 'ollama':
            self.provider = OllamaProvider()
        else:
            self.provider = OllamaProvider()

    def process_document(self, text: str, doc_type: str = 'receipt', context: dict = None) -> dict:
        """
        Takes OCR text and returns structured data using the configured provider.
        """
        # If text is empty, we only proceed if a file_path is provided for Vision models
        has_file = context and context.get('file_path')
        if not text.strip() and not has_file:
            return {
                "vendor": None,
                "invoice_no": None,
                "date": None,
                "total_amount": 0.0,
                "tax_amount": 0.0,
                "line_items": [],
                "confidence": 0.0
            }

        return self.provider.extract(text, doc_type=doc_type, context=context)
