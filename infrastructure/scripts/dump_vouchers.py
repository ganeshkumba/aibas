import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()

from apps.ledger.models import Voucher, JournalEntry

vouchers = Voucher.objects.all().order_by('-id')[:3]
for v in vouchers:
    print(f"Voucher: {v.voucher_number} ({v.voucher_type}) - Date: {v.date}")
    print(f"Narration: {v.narration}")
    print(f"Status: {'Draft' if v.is_draft else 'Final'}")
    entries = v.entries.all().select_related('account')
    total_dr = Decimal('0')
    total_cr = Decimal('0')
    for e in entries:
        print(f"  {e.account.name:30} | Dr: {e.debit:10} | Cr: {e.credit:10}")
        total_dr += e.debit
        total_cr += e.credit
    print(f"  {'TOTAL':30} | Dr: {total_dr:10} | Cr: {total_cr:10}")
    print("-" * 50)
