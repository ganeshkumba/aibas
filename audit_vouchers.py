import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document

print("--- Data Extraction Audit ---")
docs = Document.objects.filter(status='processed')
for d in docs:
    print(f"ID: {d.id} | Status: {d.status} | Lines: {d.lines.count()} | Vouchers: {d.vouchers.count()}")
    if d.lines.count() > 0 and d.vouchers.count() == 0:
        print("  !!! ALERT: Lines exist but NO VOUCHERS created.")

print("\n--- Failed/Processing Audit ---")
docs = Document.objects.exclude(status='processed')
for d in docs:
    print(f"ID: {d.id} | Status: {d.status} | Error: {d.extraction_errors.get('step') if d.extraction_errors else 'None'}")
