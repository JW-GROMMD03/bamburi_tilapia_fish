from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from datetime import date, datetime
from .supabase_service import SupabaseDB
import json

@api_view(['GET', 'POST'])
def stock_list(request):
    """Get all stock or add new stock"""
    if request.method == 'GET':
        stocks = SupabaseDB.get_stock()
        return Response(stocks if stocks else [])
    
    try:
        data = request.data
        # Calculate total cost
        qty = data.get('quantity_added', 0)
        purchase_price = data.get('purchase_price_per_unit', 0)
        total_cost = qty * purchase_price
        
        stock_data = {
            'item_name': data.get('item_name'),
            'category': data.get('category'),
            'quantity_added': qty,
            'unit_measure': data.get('unit_measure', 'pieces'),
            'purchase_price_per_unit': purchase_price,
            'selling_price_per_unit': data.get('selling_price_per_unit', 0),
            'total_purchase_cost': total_cost,
            'remaining_quantity': qty,
            'batch_number': data.get('batch_number', f'BATCH-{datetime.now().strftime("%Y%m%d%H%M%S")}'),
            'date_added': str(date.today()),
            'created_by': data.get('created_by')
        }
        result = SupabaseDB.save_stock(stock_data)
        if result:
            return Response(result, status=201)
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
def use_stock(request):
    """Record stock usage (when fish is taken from fridge)"""
    try:
        data = request.data
        stock_id = data.get('stock_id')
        qty_used = data.get('quantity_used', 0)
        
        # Update remaining quantity
        current = SupabaseDB.get_stock_by_id(stock_id)
        if current:
            new_remaining = current['remaining_quantity'] - qty_used
            SupabaseDB.update_stock(stock_id, {'remaining_quantity': new_remaining})
            
            # Record usage
            usage_data = {
                'stock_id': stock_id,
                'date': str(date.today()),
                'quantity_used': qty_used,
                'remaining_after': new_remaining,
                'recorded_by': data.get('recorded_by')
            }
            SupabaseDB.save_stock_usage(usage_data)
            return Response({'message': 'Stock updated', 'remaining': new_remaining})
        return Response({'error': 'Stock not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET', 'POST'])
def soda_stock(request):
    """Get or add soda stock"""
    if request.method == 'GET':
        sodas = SupabaseDB.get_soda_inventory()
        return Response(sodas if sodas else [])
    
    try:
        data = request.data
        crates = data.get('crates_added', 0)
        bottles_per_crate = data.get('bottles_per_crate', 24)
        total_bottles = crates * bottles_per_crate
        
        soda_data = {
            'brand': data.get('brand', 'pepsi'),
            'crates_added': crates,
            'bottles_per_crate': bottles_per_crate,
            'total_bottles': total_bottles,
            'bottles_remaining': total_bottles,
            'purchase_price_per_crate': data.get('purchase_price_per_crate', 0),
            'selling_price_per_bottle': data.get('selling_price_per_bottle', 0),
            'date_added': str(date.today())
        }
        result = SupabaseDB.save_soda(soda_data)
        if result:
            return Response(result, status=201)
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET', 'POST'])
def credit_sales(request):
    """Get or create credit sales"""
    if request.method == 'GET':
        credits = SupabaseDB.get_credit_sales()
        return Response(credits if credits else [])
    
    try:
        data = request.data
        credit_data = {
            'date': str(date.today()),
            'time': datetime.now().strftime('%H:%M'),
            'customer_name': data.get('customer_name', ''),
            'customer_phone': data.get('customer_phone', ''),
            'items': json.dumps(data.get('items', [])),
            'total': data.get('total', 0),
            'status': 'pending',
            'amount_paid': data.get('amount_paid', 0),
            'cashier_id': data.get('cashier_id'),
            'cashier_name': data.get('cashier_name', '')
        }
        result = SupabaseDB.save_credit(credit_data)
        if result:
            return Response(result, status=201)
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['PATCH'])
def update_credit(request, credit_id):
    """Update credit payment status"""
    try:
        data = request.data
        success = SupabaseDB.update_credit(credit_id, data)
        if success:
            return Response({'message': 'Updated'})
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
def stock_analysis(request):
    """Stock analysis - purchase vs sales"""
    stocks = SupabaseDB.get_stock()
    analysis = []
    for s in (stocks or []):
        sold = s.get('quantity_added', 0) - s.get('remaining_quantity', 0)
        revenue = sold * s.get('selling_price_per_unit', 0)
        cost = s.get('total_purchase_cost', 0)
        profit = revenue - cost
        analysis.append({
            'item': s.get('item_name'),
            'batch': s.get('batch_number'),
            'added': s.get('quantity_added'),
            'remaining': s.get('remaining_quantity'),
            'sold': sold,
            'purchase_price': s.get('purchase_price_per_unit'),
            'selling_price': s.get('selling_price_per_unit'),
            'total_cost': cost,
            'revenue': revenue,
            'profit': profit,
            'date_added': s.get('date_added')
        })
    return Response(analysis)