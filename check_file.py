import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document

doc = Document.objects.get(id=118)
print(f"Doc ID: {doc.id}")
print(f"File Path: {doc.file.path}")
print(f"File Size: {os.path.getsize(doc.file.path)} bytes")

# Check if it's an image or PDF
ext = os.path.splitext(doc.file.path)[1].lower()
print(f"Extension: {ext}")
