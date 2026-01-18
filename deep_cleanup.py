from core.models import Business
try:
    biz = Business.objects.get(id=7)
    print(f"Deleting business: {biz.name} (ID: 7)")
    # Force delete related items if PROTECT is getting in the way
    from apps.ledger.models import Voucher, Account, AccountGroup, FinancialYear
    Voucher.objects.filter(business=biz).delete()
    Account.objects.filter(business=biz).delete()
    AccountGroup.objects.filter(business=biz).delete()
    FinancialYear.objects.filter(business=biz).delete()
    biz.delete()
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
