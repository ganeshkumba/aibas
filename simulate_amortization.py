import os
import django
from decimal import Decimal
import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from core.models import Business, Document, ExtractedLineItem
from apps.ledger.models import Voucher, Account, AmortizationSchedule, AmortizationMovement, AccountGroup
from apps.ledger.services.ledger_service import LedgerService
from apps.ledger.services.automation_service import AutomationService

def run_simulation():
    print("Starting Beast Mode Amortization Simulation...")

    # 1. Setup Business
    business, _ = Business.objects.get_or_create(
        name="Beast Mode Tech",
        defaults={'gstin': '29ABCDE1234F1Z5', 'state': 'Karnataka'}
    )
    LedgerService.initialize_standard_coa(business)
    fy = LedgerService.initialize_financial_year(business)
    # Cleanup to avoid duplicate fingerprint errors from previous runs
    Voucher.objects.filter(business=business).delete()
    print(f"Business '{business.name}' initialized and cleared.")

    # 2. Create Mock Document
    import uuid
    doc = Document.objects.create(
        business=business,
        document_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
        document_date=datetime.date(2026, 1, 1),
        doc_type='receipt',
        status='processed',
        is_processed=True
    )
    
    # Create Line Item with "ANNUAL" keyword
    line = ExtractedLineItem.objects.create(
        document=doc,
        vendor="Cloud Hub Inc",
        amount=Decimal('12000.00'),
        description="ANNUAL CLOUD HOSTING SUBSCRIPTION",
        ledger_account="Cloud Hosting Expense",
        gst_rate="0%"
    )
    print(f"Mock Document created with description: '{line.description}'")

    # 3. Trigger Ledger Bridge (which calls Amortization Engine)
    print("Triggering Automation Bridge...")
    vouchers = AutomationService.convert_document_to_voucher(doc)
    
    if vouchers:
        voucher = vouchers if not isinstance(vouchers, list) else vouchers[0]
        print(f"Voucher created: {voucher.voucher_number}")
        
        # 4. Verify Amortization
        schedule = AmortizationSchedule.objects.filter(voucher=voucher).first()
        if schedule:
            print("\n--- AMORTIZATION DETECTED SUCCESSFULY! ---")
            print(f"Asset Account: {schedule.asset_account.name}")
            print(f"Expense Account: {schedule.expense_account.name}")
            print(f"Total Amount: INR {schedule.total_amount}")
            print(f"Periods: {schedule.periods} months")
            
            movements = AmortizationMovement.objects.filter(schedule=schedule).count()
            print(f"Movements Generated: {movements}")
            
            # Check the actual entry reclassification
            prepaid_entry = voucher.entries.filter(account=schedule.asset_account).exists()
            if prepaid_entry:
                print(f"Verified: Voucher debit was moved to {schedule.asset_account.name}")
            
            # 5. Simulate monthly posting
            print("\nSimulating monthly posting for Feb 2026...")
            posted = LedgerService.post_scheduled_amortizations(business, target_date=datetime.date(2026, 2, 1))
            print(f"Posted {posted} amortization journal(s).")
        else:
            print("❌ Amortization Schedule was NOT created.")
    else:
        print("❌ Voucher creation failed.")

if __name__ == "__main__":
    run_simulation()
