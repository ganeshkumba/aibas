
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'acctproj.settings')
django.setup()


from apps.inventory.models import Product, StockMovement
from core.models import Business, Document
from apps.ledger.services.cfo_service import CFOService
from decimal import Decimal


def test_inventory_logic():
    print("Testing Inventory Logic...")
    try:
        # Fetch a business
        business = Business.objects.first()
        if not business:
            print("No business found to test.")
            return

        print(f"Business: {business.name}")
        products = Product.objects.filter(business=business)
        print(f"Products count: {products.count()}")
        
        for p in products:
            print(f"Product: {p.name}")
            try:
                stock = p.current_stock
                print(f"  Current Stock: {stock}")
                val = stock * p.default_purchase_price
                print(f"  Value: {val}")
            except Exception as e:
                print(f"  ERROR accessing current_stock: {e}")
                import traceback
                traceback.print_exc()

        # Test view calculation
        total_stock_value = sum(p.current_stock * p.default_purchase_price for p in products)
        print(f"Total Stock Value: {total_stock_value}")

    except Exception as e:
        print(f"Inventory Logic Crash: {e}")
        import traceback
        traceback.print_exc()

def test_document_logic():
    print("\nTesting Document Logic (CFO Service)...")
    try:
        business = Business.objects.first()
        if not business:
            return
            
        print("Calling CFOService.get_executive_summary...")
        summary = CFOService.get_executive_summary(business)
        print("Summary retrieved successfully/keys:", summary.keys())
        
        # Test document specific logic
        doc = Document.objects.filter(business=business).first()
        if doc:
            print(f"Testing Document: {doc.id}")
            # Logic from views.py
            vouchers = doc.vouchers.all()
            doc_total = sum((v.total_amount for v in vouchers), Decimal('0.00'))
            print(f"Doc Total: {doc_total}")
            
    except Exception as e:
        print(f"Document Logic Crash: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_inventory_logic()
    test_document_logic()
