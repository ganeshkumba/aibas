from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
import json
from core.models import Business
from .models import Product, StockMovement

@login_required
def inventory_dashboard(request, business_id):
    if request.user.is_superuser:
        business = get_object_or_404(Business, pk=business_id)
    else:
        business = get_object_or_404(Business, pk=business_id, created_by=request.user)
    
    products = Product.objects.filter(business=business).order_by('name')
    movements = StockMovement.objects.filter(product__business=business).order_by('-date')[:20]
    
    # Calculate some stats
    low_stock_items = [p for p in products if p.current_stock <= p.low_stock_threshold]
    total_stock_value = sum(p.current_stock * p.default_purchase_price for p in products)

    # Calculate Chart Data
    # 1. Stock Distribution (by Value)
    stock_distribution = []
    for p in products[:5]: # Top 5 for the chart
        stock_distribution.append({
            'name': p.name,
            'value': float(p.current_stock * p.default_purchase_price)
        })
    
    # 2. Turnover Data (Simple Ratio for the bar)
    total_in = sum(m.quantity for m in StockMovement.objects.filter(product__business=business, type='IN'))
    total_out = sum(m.quantity for m in StockMovement.objects.filter(product__business=business, type='OUT'))
    
    return render(request, 'inventory/dashboard.html', {
        'business': business,
        'products': products,
        'movements': movements,
        'stats': {
            'low_stock_count': len(low_stock_items),
            'total_value': total_stock_value,
            'item_count': products.count(),
            'total_in': total_in,
            'total_out': total_out,
            'turnover_ratio': (total_out / total_in * 100) if total_in > 0 else 0
        },
        'chart_data': json.dumps({
            'labels': [x['name'] for x in stock_distribution],
            'values': [x['value'] for x in stock_distribution]
        })
    })
