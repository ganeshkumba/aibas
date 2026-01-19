import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from apps.ai_bridge.providers.Ollama_provider import OllamaProvider

provider = OllamaProvider()
test_text = "Sample invoice from ABC Corp for 5000 INR on 2024-01-01"
print(f"Testing Ollama with model: {provider.model}")
print(f"URL: {provider.url}")

try:
    result = provider.extract(test_text, doc_type='receipt')
    print("--- Result ---")
    print(result)
except Exception as e:
    print(f"Error: {e}")
