import os
import django
from django.conf import settings
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

print(f"AI_PROVIDER: {getattr(settings, 'AI_PROVIDER', 'Not Set')}")
print(f"OLLAMA_URL: {getattr(settings, 'OLLAMA_URL', 'Not Set')}")
print(f"OLLAMA_MODEL: {getattr(settings, 'OLLAMA_MODEL', 'Not Set')}")

url = getattr(settings, 'OLLAMA_URL', 'http://localhost:11434/api/generate')
print(f"Testing connection to {url}...")
try:
    # Try a simple GET or POST with empty body to check connectivity
    resp = requests.get(url, timeout=5)
    print(f"Connection result: {resp.status_code}")
except Exception as e:
    print(f"Connection failed: {e}")
