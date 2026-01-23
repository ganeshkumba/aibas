import os
import django
import uuid
from decimal import Decimal
from datetime import date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Business, Document
from apps.ledger.models import Voucher, Account, AccountGroup, FinancialYear, VoucherType, JournalEntry

def simulate_forensics():
    print("--- STARTING FORENSIC SHIELD SIMULATION ---")
    
    # 1. Get or create a sample business
    biz, _ = Business.objects.get_or_create(
        name="Forensic Test Corp",
        defaults={'gstin': '27AAAAA0000A1Z5', 'state': 'Maharashtra'}
    )
    print(f"Business: {biz.name}")

    # 2. Simulate a Suspicious Document (Internal PDF Producer)
    doc_suspicious = Document.objects.create(
        business=biz,
        file="forensic_test.pdf",
        status="processed",
        upload_ip="192.168.1.50", # Internal IP simulation
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Simulation/1.0",
        file_metadata={
            "Producer": "Microsoft Word 2019", # Usually fine, but let's say our logic flags specific internal strings
            "Author": "Internal Accountant (Collusion Test)"
        },
        is_suspicious=True,
        suspicion_reason="ERR-351: Document Author matches Internal Staff (Potential Collusion Risk)"
    )
    print(f"Created Suspicious Document: {doc_suspicious.id}")

    # 3. Simulate an Intercompany Transaction
    # Create another business
    sister_biz, _ = Business.objects.get_or_create(
        name="Sister Entity Ltd",
        defaults={'gstin': '27BBBBB1111B1Z5', 'state': 'Maharashtra', 'parent': biz}
    )
    biz.is_intercompany_enabled = True
    biz.save()
    
    doc_inter = Document.objects.create(
        business=biz,
        file="intercompany_invoice.pdf",
        status="processed",
        accounting_logic="INTERCOMPANY: Detected transaction with Sister Entity Ltd (ERR-252)"
    )
    from core.models import ExtractedLineItem
    ExtractedLineItem.objects.create(
        document=doc_inter,
        vendor="Sister Entity Ltd",
        amount=150000.00,
        description="Intercompany management fees"
    )
    print(f"Created Intercompany Document: {doc_inter.id}")

    print("--- SIMULATION COMPLETE ---")
    print("Forensic Dashboard should now show 1 suspicious document and 1 intercompany transaction.")

if __name__ == "__main__":
    simulate_forensics()
