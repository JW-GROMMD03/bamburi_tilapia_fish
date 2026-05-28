
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import date, datetime
from api.supabase_service import SupabaseDB
import json

@api_view(['GET','POST'])
def transactions(request):
    if request.method == 'GET':
        d = request.query_params.get('date', str(date.today()))
        return Response(SupabaseDB.get_tx(d))
    try:
        data = request.data
        tx = {
            'date': str(data.get('date', date.today())),
            'time': data.get('time', ''),
            'total': data.get('total', 0),
            'method': data.get('method', 'cash'),
            'cash_amount': data.get('cashAmt', 0),
            'mpesa_amount': data.get('mpesaAmt', 0),
            'items': json.dumps(data.get('items', [])),
            'created_at': datetime.now().isoformat()
        }
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
        d = request.query_params.get('date', str(date.today()))
        return Response(SupabaseDB.get_exp(d))
    try:
        data = request.data
        ex = {
            'date': str(data.get('date', date.today())),
            'time': data.get('time', ''),
            'name': data.get('name', ''),
            'amount': data.get('amount', 0),
            'created_at': datetime.now().isoformat()
        }
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
            t = {
                'item_type': data.get('item_type','sale'),
                'description': data.get('description',''),
                'data': json.dumps(data.get('data',{})),
                'trashed_at': datetime.now().isoformat()
            }
            r = SupabaseDB.save_trash(t)
            if r: return Response(r, status=status.HTTP_201_CREATED)
            return Response({'error':'Failed'}, status=400)
        except Exception as e:
            return Response({'error':str(e)}, status=400)
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
