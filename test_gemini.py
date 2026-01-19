import os
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from apps.ai_bridge.services.ai_service import AIService

def test_gemini():
    print("--- Gemini Connection Test ---")
    print(f"Provider: {settings.AI_PROVIDER}")
    
    test_text = """
    Reliable Realty
    Invoice #INV-2024-001
    Date: 2024-05-15
    Description: Office Rent for May 2024
    Amount: 25000.00
    GST 18%: 4500.00
    Total: 29500.00
    """
    
    service = AIService()
    try:
        result = service.process_document(test_text, doc_type='receipt')
        print("Success! Gemini response:")
        print(result)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_gemini()
