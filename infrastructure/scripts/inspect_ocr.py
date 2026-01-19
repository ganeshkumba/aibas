import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document

doc = Document.objects.get(id=123)
print(f"OCR TEXT:\n{doc.ocr_text}")
print("-" * 50)
print(f"EXTRACTION ERRORS: {doc.extraction_errors}")
