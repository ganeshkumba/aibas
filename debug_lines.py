import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document, ExtractedLineItem

doc = Document.objects.filter(id=124).first()
if doc:
    print(f"Doc ID: {doc.id}, Type: {doc.doc_type}, Status: {doc.status}")
    lines = doc.lines.all()
    print(f"Number of lines: {len(lines)}")
    for l in lines:
        print(f"  Line ID: {l.id}, Vendor: {l.vendor}, Amount: {l.amount}, GST: {l.gst_rate}, Ledger: {l.ledger_account}")
else:
    print("Doc 124 not found")
