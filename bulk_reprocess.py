import os
import django
import threading

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Document
from core.processor import process_document

failed_docs = Document.objects.filter(status='failed')
print(f"Found {failed_docs.count()} failed documents. Triggering re-processing...")

for doc in failed_docs:
    print(f"Reprocessing Doc {doc.id}...")
    # Use the same logic as views.py
    thread = threading.Thread(target=process_document, args=(doc.id,))
    thread.daemon = True
    thread.start()

print("Background threads started. Please wait a few minutes for results.")
