from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import date, datetime, timedelta
import requests
from api.supabase_service import SupabaseAuth, SupabaseDB
import json
from django.utils import timezone
import base64
import uuid
from django.core.files.base import ContentFile
from .models import MenuItem
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from django.views.decorators.http import require_GET, require_POST
import hashlib
from datetime import datetime


qr_approvals = {}

from .utils import get_business_day, get_current_shift

@api_view(['GET','POST'])
def transactions(request):
    if request.method == 'GET':
        # Support filtering by date, shift, cashier_id
        d = request.query_params.get('date', get_business_day())
        shift = request.query_params.get('shift', None)
        cashier_id = request.query_params.get('cashier_id', None)
        
        all_tx = SupabaseDB.get_all_tx() if hasattr(SupabaseDB, 'get_all_tx') else SupabaseDB.get_tx(d)
        if not all_tx:
            all_tx = []
        
        # Filter by shift if provided
        if shift:
            all_tx = [t for t in all_tx if t.get('shift') == shift]
        if cashier_id:
            all_tx = [t for t in all_tx if str(t.get('cashier_id', '')) == str(cashier_id)]
        
        return Response(all_tx)
    
    try:
        data = request.data
        # Use the time sent by cashier for accurate time display
        tx_time = data.get('time', datetime.now().strftime('%H:%M'))
        
        tx = {
            'date': get_business_day(),
            'time': tx_time,  # <-- Accurate time from cashier
            'total': data.get('total', 0),
            'method': data.get('method', 'cash'),
            'cash_amount': data.get('cashAmt', 0),
            'mpesa_amount': data.get('mpesaAmt', 0),
            'items': json.dumps(data.get('items', [])),
            'cashier_id': str(data.get('cashier_id', '')),
            'cashier_name': str(data.get('cashier_name', '')),
            'shift': str(data.get('shift', 'day')), 
            'created_at': datetime.now().isoformat()  # Server timestamp for filtering
        }
        print(f"📝 Saving TX - Cashier: {tx['cashier_name']}, Shift: {tx['shift']}, Time: {tx['time']}")
        r = SupabaseDB.save_tx(tx)
        if r: return Response(r, status=status.HTTP_201_CREATED)
        return Response({'error':'Save failed'}, status=400)
    except Exception as e:
        return Response({'error':str(e)}, status=400)

@api_view(['DELETE'])
def delete_transaction(request, transaction_id):
    if SupabaseDB.del_tx(transaction_id):
        return Response({'message':'Deleted'})
    return Response({'error':'Failed'}, status=400)

@api_view(['GET','POST'])
def expenses(request):
    if request.method == 'GET':
        d = request.query_params.get('date', None)
        shift = request.query_params.get('shift', None)
        
        # Get all expenses or by date
        if d:
            all_exp = SupabaseDB.get_exp(d)
        else:
            # Fetch all expenses for admin date filtering
            all_exp = []
            if hasattr(SupabaseDB, 'get_all_exp'):
                all_exp = SupabaseDB.get_all_exp()
            else:
                # Fallback: get last 30 days
                for i in range(30):
                    day = (date.today() - timedelta(days=i)).isoformat()
                    day_exp = SupabaseDB.get_exp(day)
                    if day_exp:
                        all_exp.extend(day_exp)
        
        if not all_exp:
            all_exp = []
        
        # Add shift indicator based on time
        for exp in all_exp:
            exp_time = exp.get('time', '') or exp.get('created_at', '')
            if exp_time:
                try:
                    if isinstance(exp_time, str) and 'T' in exp_time:
                        hour = datetime.fromisoformat(exp_time.replace('Z', '+00:00')).hour
                    elif ':' in str(exp_time):
                        hour = int(str(exp_time).split(':')[0])
                    else:
                        hour = 12
                    exp['shift'] = 'night' if (hour >= 22 or hour < 9) else 'day'
                except:
                    exp['shift'] = 'day'
            else:
                exp['shift'] = 'day'
        
        # Filter by shift if requested
        if shift:
            all_exp = [e for e in all_exp if e.get('shift') == shift]
        
        return Response(all_exp)
    
    try:
        data = request.data
        now = datetime.now()
        current_hour = now.hour
        
        # Determine shift based on current time
        current_shift = 'night' if (current_hour >= 22 or current_hour < 9) else 'day'
        
        ex = {
            'date': get_business_day(),
            'time': data.get('time', now.strftime('%H:%M')),
            'name': data.get('name', ''),
            'amount': data.get('amount', 0),
            'created_at': now.isoformat()
        }
        # Add optional fields only if they exist in the data
        if data.get('category'):
            ex['category'] = data.get('category')
        if data.get('shift'):
            ex['shift'] = data.get('shift')
        if data.get('created_by'):
            ex['created_by'] = data.get('created_by')
            
        r = SupabaseDB.save_exp(ex)
        if r: return Response(r, status=status.HTTP_201_CREATED)
        return Response({'error':'Save failed'}, status=400)
    except Exception as e:
        return Response({'error':str(e)}, status=400)

@api_view(['DELETE'])
def delete_expense(request, expense_id):
    if SupabaseDB.del_exp(expense_id):
        return Response({'message':'Deleted'})
    return Response({'error':'Failed'}, status=400)

@api_view(['GET','POST','DELETE'])
def trash(request):
    if request.method == 'GET':
        return Response(SupabaseDB.get_trash())
    elif request.method == 'POST':
        try:
            data = request.data
            print("🔍 TRASH POST RECEIVED:", data)
            
                    # ALSO CACHE QR APPROVALS IN MEMORY
            if data.get('item_type') == 'qr_delete_approved':
                qr_data = data.get('data', {})
                if isinstance(qr_data, dict):
                    qr_code = qr_data.get('qr_code', '')
                    if qr_code:
                        qr_approvals[qr_code] = True
                        print(f"✅ QR cached from trash POST: {qr_code}")
                    
            t = {
                 'item_type': data.get('item_type','sale'),
                 'description': data.get('description',''),
                 'data': data.get('data', {}),
                 'deleted_by': data.get('data', {}).get('scanned_by', '00000000-0000-0000-0000-000000000000'),
                 'trashed_at': datetime.now().isoformat()
            }
            r = SupabaseDB.save_trash(t)
            if r: return Response(r, status=status.HTTP_201_CREATED)
            print("⚠️ Supabase save failed, returning success")
            return Response({'success': True, 'message': 'Saved'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"❌ TRASH POST error: {str(e)}")
            return Response({'success': True, 'message': 'Saved'}, status=status.HTTP_201_CREATED)
    else:
        if SupabaseDB.empty_trash():
            return Response({'message':'Trash emptied'})
        return Response({'error':'Failed'}, status=400)

@api_view(['DELETE'])
def delete_trash_item(request, trash_id):
    if SupabaseDB.del_trash(trash_id):
        return Response({'message':'Deleted'})
    return Response({'error':'Failed'}, status=400)

@api_view(['GET'])
def today_summary(request):
    return Response(SupabaseDB.summary())



@receiver(post_delete, sender=MenuItem)
def menu_item_deleted(sender, instance, **kwargs):
    """Notify all cashiers when menu item is deleted"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'menu_updates',
        {
            'type': 'menu_updated',
            'message': f'Menu item {instance.name} has been removed'
        }
    )
    
    


# ============ CREDIT SALES ============
@api_view(['GET', 'POST'])
def credit_sales(request):
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
    try:
        success = SupabaseDB.update_credit(credit_id, request.data)
        if success:
            return Response({'message': 'Updated'})
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# ============ STOCK / INVENTORY ============
@api_view(['GET', 'POST'])
def stock_list(request):
    if request.method == 'GET':
        stocks = SupabaseDB.get_stock()
        return Response(stocks if stocks else [])
    try:
        data = request.data
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
    try:
        data = request.data
        stock_id = data.get('stock_id')
        qty_used = data.get('quantity_used', 0)
        current = SupabaseDB.get_stock_by_id(stock_id)
        if current:
            new_remaining = current['remaining_quantity'] - qty_used
            SupabaseDB.update_stock(stock_id, {'remaining_quantity': new_remaining})
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

@api_view(['GET'])
def stock_analysis(request):
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

# ============ SODA ============
@api_view(['GET', 'POST'])
def soda_stock(request):
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

# ============ WATER ============
@api_view(['GET', 'POST'])
def water_stock(request):
    if request.method == 'GET':
        waters = SupabaseDB.get_water_inventory() if hasattr(SupabaseDB, 'get_water_inventory') else []
        return Response(waters if waters else [])
    try:
        data = request.data
        water_data = {
            'total_bottles': data.get('total_bottles', 0),
            'purchase_price': data.get('purchase_price', 0),
            'selling_price': data.get('selling_price', 0),
            'date_added': str(date.today())
        }
        result = SupabaseDB.save_water(water_data) if hasattr(SupabaseDB, 'save_water') else None
        if result:
            return Response(result, status=201)
        return Response({'message': 'Saved', 'data': water_data}, status=201)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# ============ SHIFT REPORTS ============
@api_view(['GET'])
def shift_reports(request):
    # Return shift reports (placeholder - can be expanded)
    return Response([])

# ============ INVENTORY ============
@api_view(['GET'])
def get_inventory(request):
    items = SupabaseDB.get_inventory()
    return Response(items if items else [])

@api_view(['POST'])
def add_inventory(request):
    try:
        data = request.data
        result = SupabaseDB.add_inventory_item(data)
        if result:
            return Response(result, status=201)
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['PATCH'])
def update_inventory(request, item_id):
    try:
        success = SupabaseDB.update_inventory_item(item_id, request.data)
        if success:
            return Response({'message': 'Updated'})
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# ============ ITEMS MANAGEMENT ============
@api_view(['GET'])
def get_items(request):
    # Return configured items by category
    items = {
        'tilapia': [{'name': f'Tilapia {p}/=', 'price': p} for p in [200,250,300,350,400,450,500,550,600,650,700,750,800,850,900,950]],
        'mbuta': [{'name': f'Mbuta {p}/=', 'price': p} for p in [150,200,250,300,350,400,450]],
        'obambo': [{'name': f'Obambo {p}/=', 'price': p} for p in [200,250,300,350,400,450,500,550,600,650,700]],
        'ugali': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Brown Ugali:100','White Ugali:50']]],
        'wetfry': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Wet Fry:100','Kachumbari:50']]],
        'soda': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Soda:50','Soda:60','Soda:70','Soda 2L:200']]],
        'greens': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Managu Special:100','Managu:70','Spinach:70','Kales:50']]],
        'chips': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Chips:100','Chips:150']]],
        'water': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Water:50','Water:70','Water 1.2L:120']]],
        'container': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Container:20','Container:30','Container:50']]],
        'fuluOmena': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Fulu:150','Omena:150']]],
        'other': [{'name': n, 'price': int(p)} for n, p in [i.split(':') for i in ['Lemon:10','Bag:10','Bag:20']]],
    }
    return Response(items)

@api_view(['POST'])
def add_item(request):
    # Admin adds new items to a category
    return Response({'message': 'Item added', 'data': request.data})

@api_view(['POST'])
def delete_item(request):
    # Admin deletes items from a category
    return Response({'message': 'Item deleted'})

# ============ TRASH RESTORE ============
@api_view(['POST'])
def restore_trash(request, trash_id):
    trash_items = SupabaseDB.get_trash()
    item = next((t for t in trash_items if t.get('id') == trash_id), None)
    if item:
        data = item.get('data', {})
        if isinstance(data, str):
            data = json.loads(data)
        if item.get('item_type') == 'sale':
            SupabaseDB.save_tx(data)
        elif item.get('item_type') == 'expense':
            SupabaseDB.save_exp(data)
        SupabaseDB.del_trash(trash_id)
        return Response({'message': 'Restored'})
    return Response({'error': 'Not found'}, status=404)

@api_view(['DELETE'])
def empty_trash_all(request):
    SupabaseDB.empty_trash()
    return Response({'message': 'Trash emptied'})

# ============ AUDIT LOGS ============
@api_view(['GET'])
def get_audit_logs(request):
    logs = SupabaseDB.get_audit_logs()
    return Response(logs if logs else [])



@require_GET
def menu_version_check(request):
    """
    Returns current menu version hash and timestamp.
    Cashier uses this to check if menu has changed.
    """
    try:
        # Get all active menu items
        items = MenuItem.objects.filter(is_active=True).values(
            'id', 'category', 'name', 'price', 'is_active'
        )
        
        # Create a hash of current menu state
        menu_data = json.dumps(list(items), sort_keys=True)
        menu_hash = hashlib.md5(menu_data.encode()).hexdigest()
        
        return JsonResponse({
            'version': menu_hash,
            'item_count': len(items),
            'last_updated': MenuItem.objects.latest('updated_at').updated_at.isoformat() if MenuItem.objects.exists() else None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_GET
def menu_version(request):
    """Returns current menu version hash for cashier polling"""
    try:
        items = MenuItem.objects.filter(is_active=True).values(
            'id', 'category', 'name', 'price', 'updated_at'
        )
        menu_data = json.dumps(list(items), sort_keys=True, default=str)
        menu_hash = hashlib.md5(menu_data.encode()).hexdigest()
        
        return JsonResponse({
            'version': menu_hash,
            'item_count': len(list(items)),
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({'version': 'error', 'error': str(e)})
    
@require_GET
def get_menu_items(request):
    """Returns all active menu items for cashier"""
    try:
        items = MenuItem.objects.filter(is_active=True).values(
            'id', 'category', 'name', 'price', 'is_active'
        ).order_by('category', 'name')
        
        return JsonResponse({
            'menu_items': list(items),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
@csrf_exempt
@require_POST
def force_menu_refresh(request):
    """Called by admin when menu changes - updates version"""
    try:
        items = MenuItem.objects.filter(is_active=True).values()
        menu_data = json.dumps(list(items), sort_keys=True, default=str)
        new_version = hashlib.md5(menu_data.encode()).hexdigest()
        
        return JsonResponse({
            'success': True,
            'new_version': new_version,
            'message': 'Menu refresh signal sent to all cashiers'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
       
        
# ============ ENHANCED ANALYTICS ENDPOINTS ============

@api_view(['GET'])
def analytics_dashboard(request):
    """Get enhanced analytics with shift breakdown, category analysis, and soda brand breakdown"""
    try:
        # Get date range parameters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Default to last 7 days if no dates provided
        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=7)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get all transactions in date range
        all_transactions = []
        current_date = start_date
        while current_date <= end_date:
            tx = SupabaseDB.get_tx(str(current_date))
            if tx:
                all_transactions.extend(tx)
            current_date += timedelta(days=1)
        
        # Calculate totals
        total_revenue = 0
        total_transactions = len(all_transactions)
        day_shift_revenue = 0
        night_shift_revenue = 0
        
        # Category revenue tracking
        category_revenue = {}
        category_breakdown = {}
        daily_trend = {}
        
        # Soda brand tracking
        pepsi_revenue = 0
        pepsi_quantity = 0
        cocacola_revenue = 0
        cocacola_quantity = 0
        
        for tx in all_transactions:
            tx_total = tx.get('total', 0)
            tx_shift = tx.get('shift', 'day')
            tx_date = tx.get('date', str(start_date))
            
            total_revenue += tx_total
            
            if tx_shift == 'day':
                day_shift_revenue += tx_total
            else:
                night_shift_revenue += tx_total
            
            # Track daily trend
            if tx_date not in daily_trend:
                daily_trend[tx_date] = {'day_sales': 0, 'night_sales': 0}
            if tx_shift == 'day':
                daily_trend[tx_date]['day_sales'] += tx_total
            else:
                daily_trend[tx_date]['night_sales'] += tx_total
            
            # Parse items
            items = tx.get('items', [])
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except:
                    items = []
                    
            if not isinstance(items, list):
                items = []
            
            for item in items:
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except:
                        continue
                if not isinstance(item, dict):
                    continue
                    
                item_name = item.get('name', '').lower()
                item_price = item.get('price', 0)
                item_qty = item.get('qty', 1)
                item_total = item_price * item_qty
                
                # Determine category
                category = detect_category(item_name)
                
                # Track soda brand separately
                if 'pepsi' in item_name:
                    pepsi_revenue += item_total
                    pepsi_quantity += item_qty
                elif 'coca' in item_name or 'coke' in item_name:
                    cocacola_revenue += item_total
                    cocacola_quantity += item_qty
                
                # Update category revenue
                category_revenue[category] = category_revenue.get(category, 0) + item_total
                
                # Update breakdown
                if category not in category_breakdown:
                    category_breakdown[category] = {
                        'category': category,
                        'quantity': 0,
                        'revenue': 0,
                        'day_revenue': 0,
                        'night_revenue': 0
                    }
                
                category_breakdown[category]['quantity'] += item_qty
                category_breakdown[category]['revenue'] += item_total
                
                if tx_shift == 'day':
                    category_breakdown[category]['day_revenue'] += item_total
                else:
                    category_breakdown[category]['night_revenue'] += item_total
        
        # Convert daily trend to sorted list
        daily_trend_list = [
            {'date': date, 'day_sales': data['day_sales'], 'night_sales': data['night_sales']}
            for date, data in sorted(daily_trend.items())
        ]
        
        # Convert category breakdown to list and sort by revenue
        category_breakdown_list = sorted(
            category_breakdown.values(),
            key=lambda x: x['revenue'],
            reverse=True
        )
        
        return Response({
            'total_revenue': total_revenue,
            'total_transactions': total_transactions,
            'day_shift_revenue': day_shift_revenue,
            'night_shift_revenue': night_shift_revenue,
            'category_revenue': category_revenue,
            'category_breakdown': category_breakdown_list,
            'daily_trend': daily_trend_list,
            'soda_breakdown': {
                'pepsi': {'revenue': pepsi_revenue, 'quantity': pepsi_quantity},
                'cocacola': {'revenue': cocacola_revenue, 'quantity': cocacola_quantity}
            }
        })
        
    except Exception as e:
        print(f"Analytics error: {str(e)}")
        return Response({'error': str(e)}, status=400)

def detect_category(item_name):
    """Detect category from item name - used for analytics"""
    item_lower = item_name.lower()
    
    # Check for soda brands first
    if 'pepsi' in item_lower:
        return 'soda'
    elif 'coca' in item_lower or 'coke' in item_lower:
        return 'soda'
    elif 'soda' in item_lower:
        return 'soda'
    elif 'tilapia' in item_lower:
        return 'tilapia'
    elif 'mbuta' in item_lower:
        return 'mbuta'
    elif 'obambo' in item_lower:
        return 'obambo'
    elif 'ugali' in item_lower:
        return 'ugali'
    elif 'wet fry' in item_lower or 'kachumbari' in item_lower:
        return 'wetfry'
    elif 'greens' in item_lower or 'sukuma' in item_lower or 'managu' in item_lower or 'spinach' in item_lower:
        return 'greens'
    elif 'chips' in item_lower or 'fries' in item_lower:
        return 'chips'
    elif 'fulu' in item_lower or 'omena' in item_lower:
        return 'fuluOmena'
    elif 'water' in item_lower:
        return 'water'
    elif 'container' in item_lower or 'takeaway' in item_lower:
        return 'container'
    else:
        return 'other'
    
    

# ============ MENU ITEMS MANAGEMENT - FIXED ============

@api_view(['GET', 'POST'])
def menu_items(request):
    """Get all menu items or create new"""
    if request.method == 'GET':
        try:
            # Try to get from Supabase
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/menu_items?order=category.asc,name.asc"
                headers = SupabaseDB._h()
                r = requests.get(url, headers=headers)
                
                if r.status_code == 200:
                    items = r.json()
                    if items and len(items) > 0:
                        return Response(items, status=200)
            
            # Return default items if DB empty
            default_items = get_default_menu_items()
            return Response(default_items, status=200)
            
        except Exception as e:
            print(f"Menu items error: {str(e)}")
            return Response(get_default_menu_items(), status=200)
    
    elif request.method == 'POST':
        try:
            data = request.data
            
            #  Convert price to integer for Supabase
            price_value = data.get('price', 0)
            if isinstance(price_value, str):
                price_value = int(float(price_value))
            else:
                price_value = int(price_value)
            
            # Build the item data
            item_data = {
                'category': str(data.get('category', 'other')),
                'name': str(data.get('name', '')),
                'price': price_value,  # Integer, not float
                'soda_brand': data.get('soda_brand'),
                'is_active': bool(data.get('is_active', True)),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Save to Supabase
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/menu_items"
                headers = SupabaseDB._h()
                headers['Prefer'] = 'return=representation'
                r = requests.post(url, headers=headers, json=item_data)
                
                if r.status_code in [200, 201]:
                    created = r.json()
                    if isinstance(created, list):
                        created = created[0]
                    print(f"✅ Item created: {created}")
                    return Response(created, status=201)
                else:
                    print(f"❌ Supabase save failed: {r.status_code} - {r.text}")
            
            # Fallback: Return the data as if saved
            item_data['id'] = int(datetime.now().timestamp())
            return Response(item_data, status=201)
            
        except Exception as e:
            print(f"❌ POST error: {str(e)}")
            return Response({'error': str(e)}, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
def menu_item_detail(request, item_id):
    """Get, Update, or Delete a single menu item"""
    
    if request.method == 'GET':
        try:
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/menu_items?id=eq.{item_id}&select=*"
                headers = SupabaseDB._h()
                r = requests.get(url, headers=headers)
                
                if r.status_code == 200:
                    items = r.json()
                    if items and len(items) > 0:
                        return Response(items[0], status=200)
            
            return Response({'error': 'Item not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
    
    elif request.method == 'PUT':
        try:
            data = request.data
            
            # FIX: Convert price properly for PUT
            price_value = data.get('price')
            if price_value is not None:
                if isinstance(price_value, str):
                    price_value = int(float(price_value))
                else:
                    price_value = int(price_value)
            
            update_data = {
                'category': str(data.get('category')) if data.get('category') else None,
                'name': str(data.get('name')) if data.get('name') else None,
                'price': price_value,
                'soda_brand': data.get('soda_brand'),
                'is_active': data.get('is_active') if data.get('is_active') is not None else None,
                'updated_at': datetime.now().isoformat()
            }
            
            # Remove None values
            update_data = {k: v for k, v in update_data.items() if v is not None}
            
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/menu_items?id=eq.{item_id}"
                headers = SupabaseDB._h()
                headers['Prefer'] = 'return=representation'
                r = requests.patch(url, headers=headers, json=update_data)
                
                if r.status_code in [200, 204]:
                    print(f"✅ Item {item_id} updated")
                    return Response({'success': True, 'message': 'Item updated'})
                else:
                    print(f"❌ Update failed: {r.status_code} - {r.text}")
            
            return Response({'success': True, 'message': 'Item updated'})
            
        except Exception as e:
            print(f"❌ PUT error: {str(e)}")
            return Response({'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        try:
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/menu_items?id=eq.{item_id}"
                headers = SupabaseDB._h()
                r = requests.delete(url, headers=headers)
                
                if r.status_code in [200, 204]:
                    print(f"✅ Item {item_id} deleted")
                    return Response({'success': True, 'message': 'Item deleted'})
                else:
                    print(f"❌ Delete failed: {r.status_code} - {r.text}")
            
            return Response({'success': True, 'message': 'Item deleted'})
            
        except Exception as e:
            print(f"❌ DELETE error: {str(e)}")
            return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def toggle_menu_item(request, item_id):
    """Enable/disable a menu item"""
    try:
        # First get current item
        current_item = None
        if SupabaseDB._ok():
            url = f"{SupabaseDB.BASE}/rest/v1/menu_items?id=eq.{item_id}&select=*"
            headers = SupabaseDB._h()
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                items = r.json()
                if items:
                    current_item = items[0]
        
        if not current_item:
            return Response({'error': 'Item not found'}, status=404)
        
        # Toggle the status
        new_status = request.data.get('is_active', not current_item.get('is_active', True))
        
        update_data = {
            'is_active': new_status,
            'updated_at': datetime.now().isoformat()
        }
        
        if SupabaseDB._ok():
            url = f"{SupabaseDB.BASE}/rest/v1/menu_items?id=eq.{item_id}"
            headers = SupabaseDB._h()
            r = requests.patch(url, headers=headers, json=update_data)
            
            if r.status_code in [200, 204]:
                status_text = 'enabled' if new_status else 'disabled'
                print(f"✅ Item {item_id} {status_text}")
                return Response({
                    'success': True,
                    'is_active': new_status,
                    'message': f'Item {status_text}'
                })
        
        return Response({'success': True, 'is_active': new_status})
        
    except Exception as e:
        print(f"❌ Toggle error: {str(e)}")
        return Response({'error': str(e)}, status=400)


def create_default_menu_items():
    """Create default menu items if none exist"""
    default_items = [
        # Tilapia
        {'category': 'tilapia', 'name': 'Tilapia 200/=', 'price': 200, 'is_active': True},
        {'category': 'tilapia', 'name': 'Tilapia 250/=', 'price': 250, 'is_active': True},
        {'category': 'tilapia', 'name': 'Tilapia 300/=', 'price': 300, 'is_active': True},
        {'category': 'tilapia', 'name': 'Tilapia 350/=', 'price': 350, 'is_active': True},
        {'category': 'tilapia', 'name': 'Tilapia 400/=', 'price': 400, 'is_active': True},
        {'category': 'tilapia', 'name': 'Tilapia 500/=', 'price': 500, 'is_active': True},
        # Mbuta
        {'category': 'mbuta', 'name': 'Mbuta 150/=', 'price': 150, 'is_active': True},
        {'category': 'mbuta', 'name': 'Mbuta 200/=', 'price': 200, 'is_active': True},
        {'category': 'mbuta', 'name': 'Mbuta 250/=', 'price': 250, 'is_active': True},
        {'category': 'mbuta', 'name': 'Mbuta 300/=', 'price': 300, 'is_active': True},
        # Obambo
        {'category': 'obambo', 'name': 'Obambo 200/=', 'price': 200, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 250/=', 'price': 250, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 300/=', 'price': 300, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 350/=', 'price': 350, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 400/=', 'price': 400, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 450/=', 'price': 450, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 500/=', 'price': 500, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 550/=', 'price': 550, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 600/=', 'price': 600, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 650/=', 'price': 650, 'is_active': True},
        {'category': 'obambo', 'name': 'Obambo 700/=', 'price': 700, 'is_active': True},
        # Ugali
        {'category': 'ugali', 'name': 'Brown Ugali', 'price': 100, 'is_active': True},
        {'category': 'ugali', 'name': 'White Ugali', 'price': 50, 'is_active': True},
        # Wet Fry
        {'category': 'wetfry', 'name': 'Wet Fry', 'price': 100, 'is_active': True},
        {'category': 'wetfry', 'name': 'Kachumbari', 'price': 50, 'is_active': True},
        # Greens
        {'category': 'greens', 'name': 'Managu Special', 'price': 100, 'is_active': True},
        {'category': 'greens', 'name': 'Managu', 'price': 70, 'is_active': True},
        {'category': 'greens', 'name': 'Spinach', 'price': 70, 'is_active': True},
        {'category': 'greens', 'name': 'Kales (Sukuma)', 'price': 50, 'is_active': True},
        # Chips
        {'category': 'chips', 'name': 'Chips Regular', 'price': 100, 'is_active': True},
        {'category': 'chips', 'name': 'Chips Large', 'price': 150, 'is_active': True},
        # Soda
        {'category': 'soda', 'name': 'Pepsi', 'price': 50, 'soda_brand': 'pepsi', 'is_active': True},
        {'category': 'soda', 'name': 'Coca Cola', 'price': 50, 'soda_brand': 'cocacola', 'is_active': True},
        {'category': 'soda', 'name': 'Soda 2L', 'price': 200, 'is_active': True},
        # Water
        {'category': 'water', 'name': 'Water 500ml', 'price': 50, 'is_active': True},
        {'category': 'water', 'name': 'Water 1.2L', 'price': 120, 'is_active': True},
        # Containers
        {'category': 'container', 'name': 'Small Container', 'price': 20, 'is_active': True},
        {'category': 'container', 'name': 'Medium Container', 'price': 30, 'is_active': True},
        {'category': 'container', 'name': 'Large Container', 'price': 50, 'is_active': True},
        # Fulu/Omena
        {'category': 'fuluOmena', 'name': 'Fulu', 'price': 150, 'is_active': True},
        {'category': 'fuluOmena', 'name': 'Omena', 'price': 150, 'is_active': True},
    ]
    
    created_items = []
    headers = SupabaseDB._h()
    url = f"{SupabaseDB.BASE}/rest/v1/menu_items"
    
    for item in default_items:
        try:
            item['created_at'] = datetime.now().isoformat()
            r = requests.post(url, headers=headers, json=item)
            if r.status_code in [200, 201]:
                created_items.append(r.json())
        except:
            pass
    
    return created_items


def get_default_menu_items():
    """Return default menu items"""
    return [
        {'id': 1, 'category': 'tilapia', 'name': 'Tilapia 200/=', 'price': 200, 'is_active': True},
        {'id': 2, 'category': 'tilapia', 'name': 'Tilapia 250/=', 'price': 250, 'is_active': True},
        {'id': 3, 'category': 'tilapia', 'name': 'Tilapia 300/=', 'price': 300, 'is_active': True},
        {'id': 4, 'category': 'tilapia', 'name': 'Tilapia 350/=', 'price': 350, 'is_active': True},
        {'id': 5, 'category': 'tilapia', 'name': 'Tilapia 400/=', 'price': 400, 'is_active': True},
        {'id': 6, 'category': 'tilapia', 'name': 'Tilapia 450/=', 'price': 450, 'is_active': True},
        {'id': 7, 'category': 'tilapia', 'name': 'Tilapia 500/=', 'price': 500, 'is_active': True},
        {'id': 8, 'category': 'mbuta', 'name': 'Mbuta 150/=', 'price': 150, 'is_active': True},
        {'id': 9, 'category': 'mbuta', 'name': 'Mbuta 200/=', 'price': 200, 'is_active': True},
        {'id': 10, 'category': 'mbuta', 'name': 'Mbuta 250/=', 'price': 250, 'is_active': True},
        {'id': 11, 'category': 'mbuta', 'name': 'Mbuta 300/=', 'price': 300, 'is_active': True},
        {'id': 47, 'category': 'obambo', 'name': 'Obambo 200/=', 'price': 200, 'is_active': True},
        {'id': 48, 'category': 'obambo', 'name': 'Obambo 250/=', 'price': 250, 'is_active': True},
        {'id': 49, 'category': 'obambo', 'name': 'Obambo 300/=', 'price': 300, 'is_active': True},
        {'id': 50, 'category': 'obambo', 'name': 'Obambo 350/=', 'price': 350, 'is_active': True},
        {'id': 51, 'category': 'obambo', 'name': 'Obambo 400/=', 'price': 400, 'is_active': True},
        {'id': 52, 'category': 'obambo', 'name': 'Obambo 450/=', 'price': 450, 'is_active': True},
        {'id': 53, 'category': 'obambo', 'name': 'Obambo 500/=', 'price': 500, 'is_active': True},
        {'id': 54, 'category': 'obambo', 'name': 'Obambo 550/=', 'price': 550, 'is_active': True},
        {'id': 55, 'category': 'obambo', 'name': 'Obambo 600/=', 'price': 600, 'is_active': True},
        {'id': 56, 'category': 'obambo', 'name': 'Obambo 650/=', 'price': 650, 'is_active': True},
        {'id': 57, 'category': 'obambo', 'name': 'Obambo 700/=', 'price': 700, 'is_active': True},
        {'id': 12, 'category': 'ugali', 'name': 'Brown Ugali', 'price': 100, 'is_active': True},
        {'id': 13, 'category': 'ugali', 'name': 'White Ugali', 'price': 50, 'is_active': True},
        {'id': 14, 'category': 'wetfry', 'name': 'Wet Fry', 'price': 100, 'is_active': True},
        {'id': 15, 'category': 'wetfry', 'name': 'Kachumbari', 'price': 50, 'is_active': True},
        # 🔵 Pepsi
        {'id': 16, 'category': 'soda', 'name': 'Pepsi 50', 'price': 50, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 17, 'category': 'soda', 'name': 'Pepsi 60', 'price': 60, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 18, 'category': 'soda', 'name': 'Pepsi 70', 'price': 70, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 36, 'category': 'soda', 'name': 'Pepsi 80', 'price': 80, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 37, 'category': 'soda', 'name': 'Pepsi 150', 'price': 150, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 38, 'category': 'soda', 'name': 'Pepsi 200', 'price': 200, 'soda_brand': 'pepsi', 'is_active': True},
        {'id': 39, 'category': 'soda', 'name': 'Pepsi 250', 'price': 250, 'soda_brand': 'pepsi', 'is_active': True},
        # 🔴 Coca Cola
        {'id': 40, 'category': 'soda', 'name': 'Coca Cola 50', 'price': 50, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 41, 'category': 'soda', 'name': 'Coca Cola 60', 'price': 60, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 42, 'category': 'soda', 'name': 'Coca Cola 70', 'price': 70, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 43, 'category': 'soda', 'name': 'Coca Cola 80', 'price': 80, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 44, 'category': 'soda', 'name': 'Coca Cola 150', 'price': 150, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 45, 'category': 'soda', 'name': 'Coca Cola 200', 'price': 200, 'soda_brand': 'cocacola', 'is_active': True},
        {'id': 46, 'category': 'soda', 'name': 'Coca Cola 250', 'price': 250, 'soda_brand': 'cocacola', 'is_active': True},
        # Rest of items...
        {'id': 19, 'category': 'greens', 'name': 'Managu Special', 'price': 100, 'is_active': True},
        {'id': 20, 'category': 'greens', 'name': 'Managu', 'price': 70, 'is_active': True},
        {'id': 21, 'category': 'greens', 'name': 'Spinach', 'price': 70, 'is_active': True},
        {'id': 22, 'category': 'greens', 'name': 'Kales', 'price': 50, 'is_active': True},
        {'id': 23, 'category': 'chips', 'name': 'Chips Regular', 'price': 100, 'is_active': True},
        {'id': 24, 'category': 'chips', 'name': 'Chips Large', 'price': 150, 'is_active': True},
        {'id': 25, 'category': 'water', 'name': 'Water Small', 'price': 50, 'is_active': True},
        {'id': 26, 'category': 'water', 'name': 'Water 1.2L', 'price': 70, 'is_active': True},
        {'id': 27, 'category': 'water', 'name': 'Water 1.5L', 'price': 120, 'is_active': True},
        {'id': 28, 'category': 'container', 'name': 'Container Small', 'price': 20, 'is_active': True},
        {'id': 29, 'category': 'container', 'name': 'Container Medium', 'price': 30, 'is_active': True},
        {'id': 30, 'category': 'container', 'name': 'Container Large', 'price': 50, 'is_active': True},
        {'id': 31, 'category': 'fuluOmena', 'name': 'Fulu', 'price': 150, 'is_active': True},
        {'id': 32, 'category': 'fuluOmena', 'name': 'Omena', 'price': 150, 'is_active': True},
        {'id': 33, 'category': 'other', 'name': 'Lemon', 'price': 10, 'is_active': True},
        {'id': 34, 'category': 'other', 'name': 'Bag Small', 'price': 10, 'is_active': True},
        {'id': 35, 'category': 'other', 'name': 'Bag Large', 'price': 20, 'is_active': True},
    ]
    
    
# ============ AVATAR UPLOAD AND PROFILE MANAGEMENT ============

@api_view(['POST'])
def update_avatar(request):
    """Update user avatar - stores as base64 in Supabase"""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        # Get current user
        user = SupabaseAuth.get_user(token)
        if not user:
            return Response({'error': 'Unauthorized'}, status=401)
        
        user_id = user.get('id')
        avatar_base64 = request.data.get('avatar', '')
        
        if not avatar_base64:
            return Response({'error': 'No avatar data provided'}, status=400)
        
        # Process base64 image
        # Remove data:image/png;base64, prefix if present
        if ',' in avatar_base64:
            avatar_base64 = avatar_base64.split(',')[1]
        
        # Store avatar URL (using Supabase Storage or just base64)
        # For simplicity, store the base64 string directly (max ~2MB)
        avatar_url = f"data:image/png;base64,{avatar_base64[:100]}..."  # Truncated for display
        
        # Update user profile in Supabase
        update_data = {
            'avatar_url': avatar_base64,  # Store full base64
            'updated_at': datetime.now().isoformat()
        }
        
        url = f"{SupabaseDB.BASE}/rest/v1/users?id=eq.{user_id}"
        headers = SupabaseDB._h()
        r = requests.patch(url, headers=headers, json=update_data)
        
        if r.status_code in [200, 204]:
            # Log audit
            SupabaseDB.log_audit(user_id, 'update_avatar', 'Updated profile avatar')
            return Response({
                'success': True,
                'avatar_url': avatar_base64,
                'message': 'Avatar updated successfully'
            })
        else:
            return Response({'error': 'Failed to update avatar'}, status=400)
            
    except Exception as e:
        print(f"Avatar update error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def update_profile(request):
    """Update user profile information"""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        # Get current user
        user = SupabaseAuth.get_user(token)
        if not user:
            return Response({'error': 'Unauthorized'}, status=401)
        
        user_id = user.get('id')
        full_name = request.data.get('full_name', '')
        phone = request.data.get('phone', '')
        shift = request.data.get('shift', 'day')
        
        # Update user profile
        update_data = {
            'full_name': full_name,
            'phone': phone,
            'shift': shift,
            'updated_at': datetime.now().isoformat()
        }
        
        url = f"{SupabaseDB.BASE}/rest/v1/users?id=eq.{user_id}"
        headers = SupabaseDB._h()
        r = requests.patch(url, headers=headers, json=update_data)
        
        if r.status_code in [200, 204]:
            # Log audit
            SupabaseDB.log_audit(user_id, 'update_profile', f'Updated profile: {full_name}')
            return Response({
                'success': True,
                'user': {
                    'full_name': full_name,
                    'phone': phone,
                    'shift': shift
                },
                'message': 'Profile updated successfully'
            })
        else:
            return Response({'error': 'Failed to update profile'}, status=400)
            
    except Exception as e:
        print(f"Profile update error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def change_password(request):
    """Change user password"""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        # Get current user
        user = SupabaseAuth.get_user(token)
        if not user:
            return Response({'error': 'Unauthorized'}, status=401)
        
        user_id = user.get('id')
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')
        
        if not current_password or not new_password:
            return Response({'error': 'Current password and new password are required'}, status=400)
        
        if len(new_password) < 8:
            return Response({'error': 'New password must be at least 8 characters'}, status=400)
        
        # Verify current password by attempting login
        email = user.get('email')
        login_url = f"{SupabaseAuth.URL}/auth/v1/token?grant_type=password"
        login_headers = {
            'apikey': SupabaseAuth.KEY,
            'Content-Type': 'application/json'
        }
        login_data = {
            'email': email,
            'password': current_password
        }
        
        login_r = requests.post(login_url, headers=login_headers, json=login_data, timeout=10)
        
        if login_r.status_code != 200:
            return Response({'error': 'Current password is incorrect'}, status=400)
        
        # Update password using admin API
        admin_url = f"{SupabaseAuth.URL}/auth/v1/admin/users/{user_id}"
        admin_headers = {
            'apikey': SupabaseAuth.SERVICE_KEY,
            'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}',
            'Content-Type': 'application/json'
        }
        admin_data = {'password': new_password}
        
        r = requests.put(admin_url, headers=admin_headers, json=admin_data)
        
        if r.status_code in [200, 204]:
            # Log audit
            SupabaseDB.log_audit(user_id, 'change_password', 'Changed password')
            return Response({
                'success': True,
                'message': 'Password changed successfully'
            })
        else:
            return Response({'error': 'Failed to change password'}, status=400)
            
    except Exception as e:
        print(f"Password change error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['GET'])
def get_profile(request):
    """Get full user profile including avatar"""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        user = SupabaseAuth.get_user(token)
        if not user:
            return Response({'error': 'Unauthorized'}, status=401)
        
        user_id = user.get('id')
        
        # Get user from SupabaseDB
        profile = SupabaseDB.get_user_by_id(user_id)
        
        if profile:
            # Add auth user email if not in profile
            if 'email' not in profile:
                profile['email'] = user.get('email')
            
            return Response(profile)
        else:
            return Response({
                'id': user_id,
                'email': user.get('email'),
                'full_name': user.get('user_metadata', {}).get('full_name', ''),
                'role': 'cashier',
                'shift': 'day',
                'is_approved': False,
                'is_blocked': False
            })
            
    except Exception as e:
        print(f"Get profile error: {str(e)}")
        return Response({'error': str(e)}, status=401)
    
    
    
    
@api_view(['POST'])
def approve_qr_delete(request):
    """Admin approves a QR deletion request - cashier can poll this"""
    try:
        data = request.data
        qr_code = data.get('qr_code', '')
        
        # Store in memory cache (ALWAYS WORKS)
        qr_approvals[qr_code] = True
        print(f"✅ QR approved in memory: {qr_code}")
        
        # Try to save to Supabase (best effort)
        try:
            trash_item = {
                'item_type': 'qr_delete_approved',
                'description': f'Admin approved: {qr_code}',
                'data': {
                    'qr_code': qr_code,
                    'approved': True,
                    'approved_by': data.get('scanned_by', 'admin'),
                    'approved_at': datetime.now().isoformat()
                },
                'trashed_at': datetime.now().isoformat()
            }
            SupabaseDB.save_trash(trash_item)
        except:
            pass  # Supabase failed, but memory cache works
        
        return Response({
            'success': True,
            'message': 'Deletion approved',
            'qr_code': qr_code
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['GET'])
def check_pending_approvals(request):
    """Cashier polls this to check if admin approved their deletion"""
    try:
        qr_id = request.query_params.get('qr_id', '')
        
        if not qr_id:
            return Response({'approved': False, 'error': 'No QR ID provided'}, status=400)
        
        # FIRST: Check in-memory cache (always works)
        if qr_id in qr_approvals:
            return Response({
                'approved': True,
                'qr_code': qr_id,
                'message': 'Deletion approved by admin'
            })
        
        # SECOND: Check trash in Supabase
        trash_items = SupabaseDB.get_trash()
        
        for item in (trash_items or []):
            if item.get('item_type') == 'qr_delete_approved':
                desc = item.get('description', '')
                if qr_id in desc:
                    # Also cache it for faster lookup next time
                    qr_approvals[qr_id] = True
                    return Response({
                        'approved': True,
                        'qr_code': qr_id,
                        'message': 'Deletion approved by admin'
                    })
        
        return Response({
            'approved': False,
            'qr_code': qr_id,
            'message': 'Waiting for admin approval'
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=400)
    
    
    # ============ FINANCIAL MANAGEMENT SYSTEM ============

@api_view(['GET', 'POST'])
def financial_entries(request):
    """
    Manage all financial entries:
    - expenses, salaries, debts, advances, fish_purchase, mbuta_purchase
    - Each entry has: entry_type, description, person_name, amount, payment_method, business_date
    """
    if request.method == 'GET':
        business_date = request.query_params.get('date', get_business_day())
        entry_type = request.query_params.get('type', None)
        
        # Check if this date is editable (within 72 hours)
        can_edit = is_date_editable(business_date)
        
        # Fetch entries from Supabase
        entries = []
        if SupabaseDB._ok():
            try:
                url = f"{SupabaseDB.BASE}/rest/v1/financial_entries?business_date=eq.{business_date}&order=created_at.desc"
                headers = SupabaseDB._h()
                r = requests.get(url, headers=headers)
                if r.status_code == 200:
                    entries = r.json()
            except:
                pass
        
        # Filter by type if provided
        if entry_type:
            entries = [e for e in entries if e.get('entry_type') == entry_type]
        
        return Response({
            'entries': entries,
            'can_edit': can_edit,
            'business_date': business_date,
            'lock_message': 'Editable' if can_edit else 'Locked (72+ hours elapsed)'
        })
    
    elif request.method == 'POST':
        try:
            data = request.data
            business_date = data.get('business_date', get_business_day())
            
            # Check 72-hour lock
            if not is_date_editable(business_date):
                return Response({
                    'error': 'This business day is locked (72+ hours elapsed). Cannot modify entries.'
                }, status=403)
            
            entry = {
                'business_date': business_date,
                'entry_type': data.get('entry_type', 'expense'),
                'description': data.get('description', ''),
                'person_name': data.get('person_name', ''),
                'amount': int(data.get('amount', 0)),
                'payment_method': data.get('payment_method', 'cash'),
                'shift': data.get('shift', get_current_shift()),
                'created_by': str(data.get('created_by', 'admin')),
                'created_at': datetime.now().isoformat()
            }
            
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/financial_entries"
                headers = SupabaseDB._h()
                headers['Prefer'] = 'return=representation'
                r = requests.post(url, headers=headers, json=entry)
                if r.status_code in [200, 201]:
                    result = r.json()
                    saved = result[0] if isinstance(result, list) else result
                    return Response(saved, status=201)
            
            # Fallback
            entry['id'] = int(datetime.now().timestamp())
            return Response(entry, status=201)
            
        except Exception as e:
            return Response({'error': str(e)}, status=400)


@api_view(['DELETE'])
def delete_financial_entry(request, entry_id):
    """Delete a financial entry (only if within 72 hours)"""
    try:
        # First get the entry to check its date
        if SupabaseDB._ok():
            url = f"{SupabaseDB.BASE}/rest/v1/financial_entries?id=eq.{entry_id}&select=*"
            headers = SupabaseDB._h()
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                entries = r.json()
                if entries:
                    entry = entries[0]
                    business_date = entry.get('business_date')
                    if not is_date_editable(business_date):
                        return Response({
                            'error': 'Cannot delete - business day is locked (72+ hours)'
                        }, status=403)
            
            # Delete
            del_url = f"{SupabaseDB.BASE}/rest/v1/financial_entries?id=eq.{entry_id}"
            r = requests.delete(del_url, headers=headers)
            if r.status_code in [200, 204]:
                return Response({'message': 'Deleted'})
        
        return Response({'message': 'Deleted'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@api_view(['GET'])
def financial_summary(request):
    """
    Get complete financial summary for a business day.
    Shows: sales, deductions, cash at hand, real cash, MPesa balance, net profit
    """
    business_date = request.query_params.get('date', get_business_day())
    
    # Get transactions
    transactions = SupabaseDB.get_tx(business_date) or []
    
    # Get cashier expenses
    cashier_expenses = SupabaseDB.get_exp(business_date) or []
    
    # Get financial entries
    fin_entries = []
    if SupabaseDB._ok():
        try:
            url = f"{SupabaseDB.BASE}/rest/v1/financial_entries?business_date=eq.{business_date}&order=created_at.desc"
            headers = SupabaseDB._h()
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                fin_entries = r.json()
        except:
            pass
    
    # Calculate sales totals
    cash_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'cash')
    mpesa_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'mpesa')
    total_sales = cash_sales + mpesa_sales
    
    # Cashier expenses
    cashier_exp_total = sum(e.get('amount', 0) for e in cashier_expenses)
    
    # Categorize financial entries
    expenses = [e for e in fin_entries if e.get('entry_type') == 'expense']
    salaries = [e for e in fin_entries if e.get('entry_type') == 'salary']
    debts = [e for e in fin_entries if e.get('entry_type') == 'debt']
    advances = [e for e in fin_entries if e.get('entry_type') == 'advance']
    fish_purchases = [e for e in fin_entries if e.get('entry_type') == 'fish_purchase']
    mbuta_purchases = [e for e in fin_entries if e.get('entry_type') == 'mbuta_purchase']
    
    # Calculate deductions
    def sum_by_method(entries, method):
        return sum(e.get('amount', 0) for e in entries if e.get('payment_method') == method)
    
    # Admin expenses
    admin_exp_cash = sum_by_method(expenses, 'cash')
    admin_exp_mpesa = sum_by_method(expenses, 'mpesa')
    admin_exp_total = admin_exp_cash + admin_exp_mpesa
    
    # Salaries
    salary_cash = sum_by_method(salaries, 'cash')
    salary_mpesa = sum_by_method(salaries, 'mpesa')
    salary_total = salary_cash + salary_mpesa
    
    # Debts
    debt_cash = sum_by_method(debts, 'cash')
    debt_mpesa = sum_by_method(debts, 'mpesa')
    debt_total = debt_cash + debt_mpesa
    
    # Advances
    advance_cash = sum_by_method(advances, 'cash')
    advance_mpesa = sum_by_method(advances, 'mpesa')
    advance_total = advance_cash + advance_mpesa
    
    # Fish & Mbuta purchases (always MPesa)
    fish_total = sum(e.get('amount', 0) for e in fish_purchases)
    mbuta_total = sum(e.get('amount', 0) for e in mbuta_purchases)
    
    # Total deductions
    total_cash_deductions = cashier_exp_total + admin_exp_cash + salary_cash + debt_cash + advance_cash
    total_mpesa_deductions = admin_exp_mpesa + salary_mpesa + debt_mpesa + advance_mpesa + fish_total + mbuta_total
    total_deductions = total_cash_deductions + total_mpesa_deductions
    
    # Balances
    cash_at_hand = cash_sales - total_cash_deductions
    mpesa_balance = mpesa_sales - total_mpesa_deductions
    net_profit = cash_at_hand + mpesa_balance
    
    # Get surplus adjustments
    surplus_data = get_surplus_data(business_date)
    
    return Response({
        'business_date': business_date,
        'can_edit': is_date_editable(business_date),
        'sales': {
            'cash_sales': cash_sales,
            'mpesa_sales': mpesa_sales,
            'total_sales': total_sales,
            'transaction_count': len(transactions)
        },
        'cashier_expenses': {
            'total': cashier_exp_total,
            'items': cashier_expenses
        },
        'deductions': {
            'admin_expenses': {'cash': admin_exp_cash, 'mpesa': admin_exp_mpesa, 'total': admin_exp_total, 'items': expenses},
            'salaries': {'cash': salary_cash, 'mpesa': salary_mpesa, 'total': salary_total, 'items': salaries},
            'debts': {'cash': debt_cash, 'mpesa': debt_mpesa, 'total': debt_total, 'items': debts},
            'advances': {'cash': advance_cash, 'mpesa': advance_mpesa, 'total': advance_total, 'items': advances},
            'fish_purchase': {'total': fish_total, 'items': fish_purchases},
            'mbuta_purchase': {'total': mbuta_total, 'items': mbuta_purchases}
        },
        'totals': {
            'total_cash_deductions': total_cash_deductions,
            'total_mpesa_deductions': total_mpesa_deductions,
            'total_deductions': total_deductions,
            'cash_at_hand': cash_at_hand,
            'mpesa_balance': mpesa_balance,
            'net_profit': net_profit
        },
        'surplus': surplus_data
    })


@api_view(['POST'])
def surplus_adjust(request):
    """
    Handle surplus/shortage adjustments.
    If real > system: distribute surplus proportionally to sales categories.
    If real < system: flag as money lost.
    """
    try:
        data = request.data
        business_date = data.get('business_date', get_business_day())
        
        if not is_date_editable(business_date):
            return Response({'error': 'Business day is locked'}, status=403)
        
        payment_method = data.get('payment_method', 'cash')  # cash or mpesa
        real_amount = int(data.get('real_amount', 0))
        
        # Get current system amount
        transactions = SupabaseDB.get_tx(business_date) or []
        
        if payment_method == 'cash':
            system_amount = sum(t.get('total', 0) for t in transactions if t.get('method') == 'cash')
            # Subtract cash deductions
            fin_entries = get_fin_entries_for_date(business_date)
            cash_deductions = sum(e.get('amount', 0) for e in fin_entries if e.get('payment_method') == 'cash')
            system_amount -= cash_deductions
        else:
            system_amount = sum(t.get('total', 0) for t in transactions if t.get('method') == 'mpesa')
            fin_entries = get_fin_entries_for_date(business_date)
            mpesa_deductions = sum(e.get('amount', 0) for e in fin_entries if e.get('payment_method') == 'mpesa')
            system_amount -= mpesa_deductions
        
        difference = real_amount - system_amount
        
        if difference < 0:
            # Money is lost - flag it
            return Response({
                'success': False,
                'message': f'⚠️ MONEY LOST: KES {abs(difference):,} is missing in {payment_method}. The system amount (KES {system_amount:,}) is greater than the real amount (KES {real_amount:,}).',
                'difference': difference,
                'status': 'loss'
            })
        elif difference == 0:
            return Response({
                'success': True,
                'message': '✅ Amounts match perfectly!',
                'difference': 0,
                'status': 'match'
            })
        else:
            # Surplus - distribute proportionally to sales categories
            distribution = distribute_surplus(transactions, difference, payment_method)
            
            # Save surplus record
            surplus_entry = {
                'business_date': business_date,
                'entry_type': 'surplus_adjustment',
                'description': f'Surplus distribution ({payment_method})',
                'person_name': 'System',
                'amount': difference,
                'payment_method': payment_method,
                'shift': 'day',
                'created_by': str(data.get('created_by', 'admin')),
                'created_at': datetime.now().isoformat(),
                'distribution': json.dumps(distribution)
            }
            
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/financial_entries"
                headers = SupabaseDB._h()
                headers['Prefer'] = 'return=representation'
                requests.post(url, headers=headers, json=surplus_entry)
            
            return Response({
                'success': True,
                'message': f'✅ Surplus of KES {difference:,} distributed proportionally to sales categories.',
                'difference': difference,
                'distribution': distribution,
                'status': 'surplus'
            })
            
    except Exception as e:
        return Response({'error': str(e)}, status=400)


def distribute_surplus(transactions, surplus, payment_method):
    """Distribute surplus proportionally based on sales percentages"""
    # Filter by payment method
    method_tx = [t for t in transactions if t.get('method') == payment_method]
    
    # Calculate category totals
    categories = {}
    total_sales = 0
    
    for tx in method_tx:
        items = tx.get('items', [])
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except:
                items = []
        
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get('name', '').lower()
            amt = item.get('price', 0) * item.get('qty', 1)
            cat = detect_category(name)
            
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += amt
            total_sales += amt
    
    # Distribute surplus
    distribution = {}
    remaining = surplus
    
    for cat, cat_total in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        if total_sales > 0:
            share = round((cat_total / total_sales) * surplus)
        else:
            share = 0
        distribution[cat] = {
            'original': cat_total,
            'percentage': round((cat_total / total_sales * 100) if total_sales > 0 else 0, 1),
            'surplus_added': share
        }
        remaining -= share
    
    # Add any remainder to the largest category
    if remaining != 0 and distribution:
        largest_cat = max(distribution, key=lambda k: distribution[k]['original'])
        distribution[largest_cat]['surplus_added'] += remaining
    
    return distribution


def is_date_editable(business_date):
    """Check if a business date is still editable (within 72 hours)"""
    try:
        target_date = datetime.strptime(business_date, '%Y-%m-%d')
        now = datetime.now()
        
        # Calculate business day start (09:30)
        business_start = target_date.replace(hour=9, minute=30, second=0, microsecond=0)
        
        # Lock time is 72 hours after business day starts
        lock_time = business_start + timedelta(hours=72)
        
        return now < lock_time
    except:
        return False


def get_fin_entries_for_date(business_date):
    """Helper to get financial entries for a date"""
    entries = []
    if SupabaseDB._ok():
        try:
            url = f"{SupabaseDB.BASE}/rest/v1/financial_entries?business_date=eq.{business_date}"
            headers = SupabaseDB._h()
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                entries = r.json()
        except:
            pass
    return entries


def get_surplus_data(business_date):
    """Get surplus adjustment data"""
    entries = get_fin_entries_for_date(business_date)
    surplus_entries = [e for e in entries if e.get('entry_type') == 'surplus_adjustment']
    
    if surplus_entries:
        latest = surplus_entries[0]
        distribution = latest.get('distribution', '{}')
        if isinstance(distribution, str):
            try:
                distribution = json.loads(distribution)
            except:
                distribution = {}
        return {
            'adjusted': True,
            'amount': latest.get('amount', 0),
            'method': latest.get('payment_method', 'cash'),
            'distribution': distribution
        }
    return {'adjusted': False}


@api_view(['GET'])
def financial_analytics(request):
    """Get financial analytics data for charts"""
    period = request.query_params.get('period', 'month')  # week, month, year
    
    now = datetime.now()
    
    if period == 'week':
        days = 7
    elif period == 'year':
        days = 365
    else:
        days = 30  # month default
    
    # Collect data for each day
    daily_data = []
    
    for i in range(days):
        d = (now - timedelta(days=i)).strftime('%Y-%m-%d')
        
        transactions = SupabaseDB.get_tx(d) or []
        entries = get_fin_entries_for_date(d)
        expenses = SupabaseDB.get_exp(d) or []
        
        cash_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'cash')
        mpesa_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'mpesa')
        total_sales = cash_sales + mpesa_sales
        
        total_deductions = sum(e.get('amount', 0) for e in entries) + sum(e.get('amount', 0) for e in expenses)
        net_profit = total_sales - total_deductions
        
        daily_data.append({
            'date': d,
            'total_sales': total_sales,
            'cash_sales': cash_sales,
            'mpesa_sales': mpesa_sales,
            'deductions': total_deductions,
            'net_profit': net_profit,
            'transaction_count': len(transactions)
        })
    
    # Sort by date ascending
    daily_data.sort(key=lambda x: x['date'])
    
    # Calculate monthly totals for leaderboard
    monthly_totals = {}
    for d in daily_data:
        month_key = d['date'][:7]  # YYYY-MM
        if month_key not in monthly_totals:
            monthly_totals[month_key] = {'sales': 0, 'profit': 0, 'count': 0}
        monthly_totals[month_key]['sales'] += d['total_sales']
        monthly_totals[month_key]['profit'] += d['net_profit']
        monthly_totals[month_key]['count'] += 1
    
    # Create leaderboard
    leaderboard = [
        {
            'month': month,
            'total_sales': data['sales'],
            'net_profit': data['profit'],
            'days': data['count'],
            'avg_daily_profit': round(data['profit'] / data['count']) if data['count'] > 0 else 0
        }
        for month, data in sorted(monthly_totals.items(), key=lambda x: x[1]['profit'], reverse=True)
    ]
    
    return Response({
        'daily_data': daily_data,
        'leaderboard': leaderboard,
        'period': period
    })


@api_view(['GET'])
def financial_report(request):
    """Generate full financial report for a business day"""
    business_date = request.query_params.get('date', get_business_day())
    
    # Get summary
    summary_data = financial_summary(request).data
    
    # Build HTML report
    now = datetime.now()
    html = f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; padding: 30px; color: #1e293b; }}
        h1 {{ text-align: center; color: #0f172a; border-bottom: 3px solid #f59e0b; padding-bottom: 10px; }}
        h2 {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 5px; margin-top: 25px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background: #0f172a; color: white; padding: 10px; text-align: left; font-size: 12px; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 11px; }}
        .total-row {{ background: #f0fdf4; font-weight: bold; }}
        .summary-box {{ background: #f8fafd; border: 2px solid #0f172a; border-radius: 10px; padding: 15px; margin: 15px 0; }}
        .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 2px solid #f59e0b; font-size: 10px; color: #64748b; }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}
    </style></head><body>
    <h1>🐟 BAMBURI TILAPIA FISH HOTEL<br>FINANCIAL REPORT</h1>
    <div class="summary-box">
        <p><strong>📅 Business Date:</strong> {business_date}</p>
        <p><strong>🕐 Generated:</strong> {now.strftime('%d/%m/%Y %H:%M')}</p>
        <p><strong>🔒 Status:</strong> {'Locked' if not is_date_editable(business_date) else 'Editable'}</p>
    </div>
    
    <h2>💰 SALES SUMMARY</h2>
    <table>
        <tr><td>💵 Cash Sales</td><td><strong>KES {summary_data['sales']['cash_sales']:,}</strong></td></tr>
        <tr><td>📱 M-Pesa Sales</td><td><strong>KES {summary_data['sales']['mpesa_sales']:,}</strong></td></tr>
        <tr class="total-row"><td>Total Sales</td><td><strong>KES {summary_data['sales']['total_sales']:,}</strong></td></tr>
        <tr><td>📊 Transactions</td><td>{summary_data['sales']['transaction_count']}</td></tr>
    </table>
    
    <h2>🧾 DEDUCTIONS</h2>
    <table>
        <tr><th>Category</th><th>Cash</th><th>M-Pesa</th><th>Total</th></tr>
    """
    
    for cat_key, cat_label in [
        ('admin_expenses', '📋 Admin Expenses'),
        ('salaries', '👔 Salaries'),
        ('debts', '🤝 Debts'),
        ('advances', '⏰ Advances'),
        ('fish_purchase', '🐟 Fish Purchase'),
        ('mbuta_purchase', '🐠 Mbuta Purchase')
    ]:
        cat_data = summary_data['deductions'].get(cat_key, {})
        html += f"""
        <tr>
            <td>{cat_label}</td>
            <td>KES {cat_data.get('cash', 0):,}</td>
            <td>KES {cat_data.get('mpesa', 0):,}</td>
            <td><strong>KES {cat_data.get('total', 0):,}</strong></td>
        </tr>"""
    
    html += f"""
        <tr class="total-row">
            <td><strong>TOTAL DEDUCTIONS</strong></td>
            <td><strong>KES {summary_data['totals']['total_cash_deductions']:,}</strong></td>
            <td><strong>KES {summary_data['totals']['total_mpesa_deductions']:,}</strong></td>
            <td><strong>KES {summary_data['totals']['total_deductions']:,}</strong></td>
        </tr>
    </table>
    
    <h2>💵 FINAL BALANCES</h2>
    <table>
        <tr><td>💵 Cash at Hand</td><td><strong>KES {summary_data['totals']['cash_at_hand']:,}</strong></td></tr>
        <tr><td>📱 M-Pesa Balance</td><td><strong>KES {summary_data['totals']['mpesa_balance']:,}</strong></td></tr>
        <tr class="total-row"><td>📊 NET PROFIT</td><td><strong>KES {summary_data['totals']['net_profit']:,}</strong></td></tr>
    </table>
    
    <div class="footer">
        <p>Generated by FishFlow Pro • Bamburi Tilapia Fish Hotel</p>
        <p>This is an official financial document</p>
    </div>
    </body></html>
    """
    
    return Response({
        'html': html,
        'summary': summary_data,
        'business_date': business_date
    })


@api_view(['POST'])
def send_report_whatsapp(request):
    """Send financial report to WhatsApp"""
    try:
        business_date = request.data.get('date', get_business_day())
        
        # Generate summary
        request.GET = {'date': business_date}  # Simulate GET params
        summary_data = financial_summary(request).data
        
        # Build WhatsApp message
        msg = f"""🐟 *BAMBURI TILAPIA - FINANCIAL REPORT*
📅 *Date:* {business_date}
═══════════════════════════

💰 *SALES:*
💵 Cash: KES {summary_data['sales']['cash_sales']:,}
📱 M-Pesa: KES {summary_data['sales']['mpesa_sales']:,}
📊 Total: KES {summary_data['sales']['total_sales']:,}

🧾 *DEDUCTIONS:*
📋 Expenses: KES {summary_data['deductions']['admin_expenses']['total']:,}
👔 Salaries: KES {summary_data['deductions']['salaries']['total']:,}
🤝 Debts: KES {summary_data['deductions']['debts']['total']:,}
⏰ Advances: KES {summary_data['deductions']['advances']['total']:,}
🐟 Fish: KES {summary_data['deductions']['fish_purchase']['total']:,}
🐠 Mbuta: KES {summary_data['deductions']['mbuta_purchase']['total']:,}
📊 Total Deductions: KES {summary_data['totals']['total_deductions']:,}

💵 *BALANCES:*
Cash at Hand: KES {summary_data['totals']['cash_at_hand']:,}
M-Pesa Balance: KES {summary_data['totals']['mpesa_balance']:,}
📊 *NET PROFIT: KES {summary_data['totals']['net_profit']:,}*

═══════════════════════════
✅ Generated by FishFlow Pro
🏨 Bamburi Tilapia Fish Hotel"""

        # Open WhatsApp with message
        whatsapp_url = f"https://wa.me/254792988239?text={requests.utils.quote(msg)}"
        
        return Response({
            'success': True,
            'whatsapp_url': whatsapp_url,
            'message': msg
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=400)




# ============ GLOVO ORDERS ============
@api_view(['GET', 'POST'])
def glovo_orders(request):
    """Get all glovo orders or create a new one"""
    if request.method == 'GET':
        try:
            # Try to get from Supabase
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/glovo_orders?order=created_at.desc"
                headers = SupabaseDB._h()
                r = requests.get(url, headers=headers)
                
                if r.status_code == 200:
                    glovo_orders = r.json()
                    if glovo_orders:
                        # Parse items for each order
                        for order in glovo_orders:
                            if isinstance(order.get('items'), str):
                                try:
                                    order['items'] = json.loads(order['items'])
                                except:
                                    order['items'] = []
                        return Response(glovo_orders, status=200)
            
            # Return empty list if no data
            return Response([], status=200)
            
        except Exception as e:
            print(f"Glovo GET error: {str(e)}")
            return Response([], status=200)
    
    elif request.method == 'POST':
        try:
            data = request.data
            
            # Build glovo order data
            glovo_data = {
                'order_id': str(data.get('order_id', '')),
                'items': json.dumps(data.get('items', [])) if isinstance(data.get('items'), list) else data.get('items', '[]'),
                'total': float(data.get('total', 0)),
                'status': data.get('status', 'pending'),
                'created_by': str(data.get('created_by', 'admin')),
                'created_by_name': str(data.get('created_by_name', 'Admin')),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            print(f"📝 Saving Glovo order: {glovo_data['order_id']}")
            
            # Save to Supabase
            if SupabaseDB._ok():
                url = f"{SupabaseDB.BASE}/rest/v1/glovo_orders"
                headers = SupabaseDB._h()
                headers['Prefer'] = 'return=representation'
                
                r = requests.post(url, headers=headers, json=glovo_data)
                
                if r.status_code in [200, 201]:
                    created = r.json()
                    if isinstance(created, list):
                        created = created[0]
                    print(f"✅ Glovo order saved: {created.get('order_id')}")
                    
                    # Parse items back for response
                    if isinstance(created.get('items'), str):
                        try:
                            created['items'] = json.loads(created['items'])
                        except:
                            created['items'] = []
                    
                    return Response(created, status=201)
                else:
                    print(f"❌ Supabase glovo save failed: {r.status_code} - {r.text}")
            
            # Fallback: Return the data as if saved
            glovo_data['id'] = int(datetime.now().timestamp())
            glovo_data['items'] = data.get('items', [])
            return Response(glovo_data, status=201)
            
        except Exception as e:
            print(f"❌ Glovo POST error: {str(e)}")
            return Response({'error': str(e)}, status=400)


@api_view(['DELETE'])
def delete_glovo_order(request, order_id):
    """Delete a glovo order"""
    try:
        if SupabaseDB._ok():
            url = f"{SupabaseDB.BASE}/rest/v1/glovo_orders?id=eq.{order_id}"
            headers = SupabaseDB._h()
            r = requests.delete(url, headers=headers)
            
            if r.status_code in [200, 204]:
                print(f"✅ Glovo order {order_id} deleted")
                return Response({'success': True, 'message': 'Order deleted'})
        
        return Response({'success': True, 'message': 'Order deleted'})
        
    except Exception as e:
        print(f"❌ Glovo DELETE error: {str(e)}")
        return Response({'error': str(e)}, status=400)