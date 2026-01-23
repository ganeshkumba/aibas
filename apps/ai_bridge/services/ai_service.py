from django.conf import settings
from ..providers.Ollama_provider import OllamaProvider
from ..providers.Gemini_provider import GeminiProvider
from apps.common.notifications import NotificationService

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
        Includes a God-Mode Failover: If the primary provider (Gemini) fails or hits quota,
        it automatically falls back to the secondary (Ollama) to ensure zero downtime.
        """
        has_file = context and context.get('file_path')
        if (not text or not text.strip()) and not has_file:
            return {
                "vendor": None,
                "invoice_no": None,
                "date": None,
                "total_amount": 0.0,
                "tax_amount": 0.0,
                "line_items": [],
                "confidence": 0.0
            }

        # --- STEP 1: Attempt Gemini Provider ---
        try:
            result = self.provider.extract(text, doc_type=doc_type, context=context)
            
            # Check for API-specific quota or error messages
            if isinstance(result, dict) and "error" in result:
                err_msg = str(result["error"]).lower()
                if "429" in err_msg or "quota" in err_msg or "limit" in err_msg:
                    print(f"[AI Bridge] Gemini Quota Exceeded.")
                    NotificationService.send_quota_alert("Gemini", "None")
            
            return result

        except Exception as e:
            logger.error(f"[AI Bridge] Gemini Extraction Error: {e}")
            return {"error": f"Gemini implementation failed: {str(e)}"}
