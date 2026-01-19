import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document

print("Checking last 5 documents:")
for d in Document.objects.all().order_by('-id')[:5]:
    v_count = d.vouchers.count()
    l_count = d.lines.count()
    print(f"ID: {d.id}, Status: {d.status}, Is Processed: {d.is_processed}")
    print(f"  Lines: {l_count}, Vouchers: {v_count}")
    print(f"  Errors: {d.extraction_errors}")
    print(f"  OCR Text (len): {len(d.ocr_text) if d.ocr_text else 0}")
    print("-" * 20)