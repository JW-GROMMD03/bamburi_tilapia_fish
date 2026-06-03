from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import date, datetime, timedelta

from .utils import get_business_day
from .supabase_service import SupabaseDB
import json

@api_view(['GET'])
def admin_dashboard(request):
    
    """Admin dashboard - complete overview"""
    today = get_business_day()
    
    transactions = SupabaseDB.get_tx(today)
    expenses = SupabaseDB.get_exp(today)
    cashiers = SupabaseDB.get_all_cashiers()
    
    category_stats = calculate_category_stats(transactions)
    cashier_performance = get_cashier_performance(transactions)
    
    total_sales = sum(t.get('total', 0) for t in transactions)
    total_expenses = sum(e.get('amount', 0) for e in expenses)
    
    # Cash vs M-Pesa breakdown
    cash_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'cash')
    mpesa_sales = sum(t.get('total', 0) for t in transactions if t.get('method') == 'mpesa')
    
    # Cash at Hand = Cash Sales - Expenses
    cash_at_hand = cash_sales - total_expenses
    
    # Fish/Mbuta cash vs M-Pesa
    fish_cash, fish_mpesa = 0, 0
    mbuta_cash, mbuta_mpesa = 0, 0
    
    for t in transactions:
        items = t.get('items', [])
        if isinstance(items, str):
            items = json.loads(items)
        method = t.get('method', 'cash')
        for item in items:
            name = item.get('name', '').lower()
            amt = item.get('price', 0) * item.get('qty', 1)
            if 'tilapia' in name:
                if method == 'cash': fish_cash += amt
                else: fish_mpesa += amt
            elif 'mbuta' in name:
                if method == 'cash': mbuta_cash += amt
                else: mbuta_mpesa += amt
    
    return Response({
        'today': {
            'date': today,
            'total_sales': total_sales,
            'cash_sales': cash_sales,
            'mpesa_sales': mpesa_sales,
            'total_expenses': total_expenses,
            'cash_at_hand': cash_at_hand,
            'net_revenue': total_sales - total_expenses,
            'transaction_count': len(transactions),
            'category_stats': category_stats,
        },
        'fish_breakdown': {
            'tilapia': {'cash': fish_cash, 'mpesa': fish_mpesa, 'total': fish_cash + fish_mpesa},
            'mbuta': {'cash': mbuta_cash, 'mpesa': mbuta_mpesa, 'total': mbuta_cash + mbuta_mpesa},
        },
        'shifts': {
            'day_shift_sales': sum(t.get('total', 0) for t in transactions if t.get('shift') == 'day'),
            'night_shift_sales': sum(t.get('total', 0) for t in transactions if t.get('shift') == 'night'),
        },
        'cashiers': {
            'total': len(cashiers),
            'active': len([c for c in cashiers if c.get('is_approved') and not c.get('is_blocked')]),
            'pending': len([c for c in cashiers if not c.get('is_approved')]),
            'blocked': len([c for c in cashiers if c.get('is_blocked')]),
            'performance': cashier_performance,
        },
    })

@api_view(['GET'])
def manager_dashboard(request):
    """Manager dashboard - operational overview"""
    today = str(date.today())
    
    transactions = SupabaseDB.get_tx(today)
    expenses = SupabaseDB.get_exp(today)
    cashiers = SupabaseDB.get_all_cashiers()
    
    category_stats = calculate_category_stats(transactions)
    cashier_performance = get_cashier_performance(transactions)
    
    total_sales = sum(t.get('total', 0) for t in transactions)
    total_expenses = sum(e.get('amount', 0) for e in expenses)
    
    # Active cashiers on shift
    day_cashiers = [c for c in cashiers if c.get('shift') == 'day' and c.get('is_approved') and not c.get('is_blocked')]
    night_cashiers = [c for c in cashiers if c.get('shift') == 'night' and c.get('is_approved') and not c.get('is_blocked')]
    
    return Response({
        'today': {
            'date': today,
            'total_sales': total_sales,
            'total_expenses': total_expenses,
            'net_revenue': total_sales - total_expenses,
            'transaction_count': len(transactions),
            'category_stats': category_stats,
        },
        'cashiers': {
            'day_shift': len(day_cashiers),
            'night_shift': len(night_cashiers),
            'performance': cashier_performance,
        },
        'pending_approvals': [c for c in cashiers if not c.get('is_approved')],
    })

@api_view(['GET'])
def cashier_dashboard(request):
    """Cashier dashboard - personal view"""
    today = str(date.today())
    cashier_id = request.query_params.get('cashier_id', '')
    
    transactions = SupabaseDB.get_tx(today)
    # Filter for this cashier
    my_transactions = [t for t in transactions if t.get('cashier_id') == cashier_id]
    
    category_stats = calculate_category_stats(my_transactions)
    
    total_sales = sum(t.get('total', 0) for t in my_transactions)
    transaction_count = len(my_transactions)
    
    # Shift info
    cashier_info = SupabaseDB.get_user_by_id(cashier_id) if cashier_id else {}
    
    return Response({
        'today': {
            'date': today,
            'total_sales': total_sales,
            'transaction_count': transaction_count,
            'category_stats': category_stats,
        },
        'shift': cashier_info.get('shift', 'N/A'),
        'is_blocked': cashier_info.get('is_blocked', False),
    })

@api_view(['GET'])
def monthly_comparison(request):
    """Monthly sales comparison for charts"""
    today = date.today()
    monthly_data = []
    
    for i in range(30):
        d = today - timedelta(days=i)
        date_str = str(d)
        transactions = SupabaseDB.get_tx(date_str)
        
        total = sum(t.get('total', 0) for t in transactions)
        tilapia_sales = sum(
            sum(item.get('price', 0) * item.get('qty', 1) 
                for item in (json.loads(t.get('items', '[]')) if isinstance(t.get('items'), str) else t.get('items', []))
                if 'tilapia' in item.get('name', '').lower())
            for t in transactions
        )
        mbuta_sales = sum(
            sum(item.get('price', 0) * item.get('qty', 1)
                for item in (json.loads(t.get('items', '[]')) if isinstance(t.get('items'), str) else t.get('items', []))
                if 'mbuta' in item.get('name', '').lower())
            for t in transactions
        )
        
        monthly_data.append({
            'date': date_str,
            'total_sales': total,
            'tilapia_sales': tilapia_sales,
            'mbuta_sales': mbuta_sales,
            'transaction_count': len(transactions),
        })
    
    return Response(monthly_data)

def calculate_category_stats(transactions):
    """Calculate sales by category"""
    categories = {
        'tilapia': {'pieces': 0, 'amount': 0},
        'mbuta': {'pieces': 0, 'amount': 0},
        'ugali': {'pieces': 0, 'amount': 0},
        'wetfry': {'pieces': 0, 'amount': 0},
        'soda': {'pieces': 0, 'amount': 0},
        'greens': {'pieces': 0, 'amount': 0},
        'chips': {'pieces': 0, 'amount': 0},
        'bag': {'pieces': 0, 'amount': 0},
        'fuluOmena': {'pieces': 0, 'amount': 0},
        'water': {'pieces': 0, 'amount': 0},
        'container': {'pieces': 0, 'amount': 0},
        'other': {'pieces': 0, 'amount': 0},
    }
    
    for t in transactions:
        items = t.get('items', [])
        if isinstance(items, str):
            items = json.loads(items)
        for item in items:
            name = item.get('name', '').lower()
            qty = item.get('qty', 1)
            price = item.get('price', 0)
            
            if 'tilapia' in name:
                cat = 'tilapia'
            elif 'mbuta' in name or 'fish' in name:
                cat = 'mbuta'
            elif 'ugali' in name:
                cat = 'ugali'
            elif 'wet fry' in name or 'kachumbari' in name:
                cat = 'wetfry'
            elif 'soda' in name:
                cat = 'soda'
            elif any(g in name for g in ['managu', 'spinach', 'kales']):
                cat = 'greens'
            elif 'chips' in name:
                cat = 'chips'
            elif 'bag' in name:
                cat = 'bag'
            elif 'fulu' in name or 'omena' in name:
                cat = 'fuluOmena'
            elif 'water' in name or 'maji' in name:
                cat = 'water'
            elif 'container' in name:
                cat = 'container'
            else:
                cat = 'other'
            
            categories[cat]['pieces'] += qty
            categories[cat]['amount'] += price * qty
    
    return categories

def get_cashier_performance(transactions):
    """Calculate performance per cashier"""
    cashier_stats = {}
    
    for t in transactions:
        cashier_id = t.get('cashier_id', 'unknown')
        cashier_name = t.get('cashier_name', 'Unknown')
        
        if cashier_id not in cashier_stats:
            cashier_stats[cashier_id] = {
                'name': cashier_name,
                'total_sales': 0,
                'transaction_count': 0,
            }
        
        cashier_stats[cashier_id]['total_sales'] += t.get('total', 0)
        cashier_stats[cashier_id]['transaction_count'] += 1
    
    return list(cashier_stats.values())



@api_view(['GET', 'POST'])
def glovo_orders(request):
    """Glovo orders - affect stock but NOT cash/MPesa sales"""
    if request.method == 'GET':
        glovo = SupabaseDB.get_glovo_orders() if hasattr(SupabaseDB, 'get_glovo_orders') else []
        return Response(glovo if glovo else [])
    try:
        data = request.data
        glovo_data = {
            'date': str(date.today()),
            'time': datetime.now().strftime('%H:%M'),
            'customer_name': data.get('customer_name', 'Glovo Customer'),
            'items': json.dumps(data.get('items', [])),
            'total': data.get('total', 0),
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        result = SupabaseDB.save_glovo(glovo_data) if hasattr(SupabaseDB, 'save_glovo') else glovo_data
        if result:
            return Response(result, status=201)
        return Response({'message': 'Saved locally', 'data': glovo_data}, status=201)
    except Exception as e:
        return Response({'error': str(e)}, status=400)