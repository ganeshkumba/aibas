import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document

print("--- Document Status Report ---")
docs = Document.objects.all().order_by('-uploaded_at')[:20]
for d in docs:
    print(f"ID: {d.id} | Status: {d.status} | Processed: {d.is_processed} | Type: {d.doc_type}")
    if d.extraction_errors:
        print(f"  ERROR: {d.extraction_errors}")
    print(f"  Lines: {d.lines.count()} | Vouchers: {d.vouchers.count()}")
    print("-" * 30)
