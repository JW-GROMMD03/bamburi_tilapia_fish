import os
import json
import requests
from datetime import date, datetime
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

class SupabaseAuth:
    URL = os.getenv('SUPABASE_URL', '').rstrip('/')
    KEY = os.getenv('SUPABASE_KEY', '')
    SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
    
    @classmethod
    def reset_user_password(cls, user_id, new_password):
        """Admin reset user password"""
        try:
            url = f"{cls.URL}/auth/v1/admin/users/{user_id}"
            headers = {
                'apikey': cls.SERVICE_KEY,
                'Authorization': f'Bearer {cls.SERVICE_KEY}',
                'Content-Type': 'application/json'
            }
            data = {'password': new_password}
            r = requests.put(url, headers=headers, json=data)
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def signup(cls, email, password, metadata):
        try:
            url = f"{cls.URL}/auth/v1/signup"
            headers = {
                'apikey': cls.KEY,
                'Content-Type': 'application/json'
            }
            data = {
                'email': email,
                'password': password,
                'data': metadata
            }
            r = requests.post(url, headers=headers, json=data)
            print(f"Signup response: {r.status_code} - {r.text[:200]}")
            if r.status_code in [200, 201]:
                result = r.json()
                user_id = result.get('id') or result.get('user', {}).get('id')
                if user_id:
                    metadata['email'] = email
                    SupabaseDB.create_user_profile(user_id, metadata)
                return result
            else:
                print(f"Signup failed: {r.text}")
                return None
        except Exception as e:
            print(f"Signup error: {e}")
            return None
    
    @classmethod
    def login(cls, email, password):
        """Login using direct password verification via RPC"""
        try:
            url = f"{cls.URL}/rest/v1/rpc/verify_user_password"
            headers = {
                'apikey': cls.SERVICE_KEY,
                'Authorization': f'Bearer {cls.SERVICE_KEY}',
                'Content-Type': 'application/json'
            }
            data = {
                'p_email': email,
                'p_password': password
            }
            r = requests.post(url, headers=headers, json=data)
            
            if r.status_code == 200:
                result = r.json()
                if result.get('success'):
                    user = result.get('user', {})
                    if user.get('is_blocked'):
                        return {'error': 'Account blocked. Contact admin.'}
                    if not user.get('is_approved') and user.get('role') != 'admin':
                        return {'error': 'Account pending approval.'}
                    
                    return {
                        'access_token': f'direct-auth-{user.get("id")}',
                        'user': user,
                        'success': True
                    }
                else:
                    return {'error': result.get('error', 'Invalid credentials')}
            else:
                return {'error': 'Login service unavailable'}
        except Exception as e:
            print(f"Login error: {e}")
            return {'error': str(e)}
    
    @classmethod
    def get_user(cls, token):
        try:
            url = f"{cls.URL}/auth/v1/user"
            headers = {'apikey': cls.KEY, 'Authorization': f'Bearer {token}'}
            r = requests.get(url, headers=headers)
            return r.json() if r.status_code == 200 else None
        except:
            return None


class SupabaseDB:
    BASE = os.getenv('SUPABASE_URL', '').rstrip('/')
    KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
    
    @classmethod
    def _h(cls):
        return {
            'apikey': cls.KEY,
            'Authorization': f'Bearer {cls.KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
    
    @classmethod
    def _ok(cls):
        return bool(cls.BASE and cls.KEY and len(cls.KEY) > 20)
    
    # ========== USER MANAGEMENT ==========
    @classmethod
    def create_user_profile(cls, user_id, metadata):
        if not cls._ok(): return None
        try:
            data = {
                'id': user_id,
                'full_name': metadata.get('full_name', ''),
                'email': metadata.get('email', ''),
                'phone': metadata.get('phone', ''),
                'role': metadata.get('role', 'cashier'),
                'shift': metadata.get('shift', 'day'),
                'is_approved': metadata.get('is_approved', False),
                'is_blocked': False,
                'login_attempts': 0
            }
            r = requests.post(f'{cls.BASE}/rest/v1/users', headers=cls._h(), json=data)
            return r.json() if r.status_code in [200, 201] else None
        except:
            return None
    
    @classmethod
    def get_user_by_email(cls, email):
        if not cls._ok(): return None
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'email': f'eq.{email}', 'limit': '1'})
            data = r.json()
            return data[0] if data else None
        except:
            return None
    
    @classmethod
    def get_user_by_id(cls, user_id):
        if not cls._ok(): return None
        try:
            url = f'{cls.BASE}/rest/v1/users?id=eq.{user_id}'
            r = requests.get(url, headers=cls._h())
            if r.status_code == 200:
                users = r.json()
                return users[0] if users else None
            return None
        except Exception as e:
            print(f"Get user by id error: {str(e)}")
            return None
    
    @classmethod
    def get_all_users(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def get_all_cashiers(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'role': 'eq.cashier', 'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def get_all_managers(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'role': 'eq.manager', 'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def approve_user(cls, user_id, approver_id):
        if not cls._ok(): return False
        try:
            url = f"{cls.BASE}/rest/v1/users?id=eq.{user_id}"
            data = {'is_approved': True, 'updated_at': datetime.now().isoformat()}
            r = requests.patch(url, headers=cls._h(), json=data)
            print(f"Approve response: {r.status_code} - {r.text}")
            return r.status_code in [200, 201, 204]
        except Exception as e:
            print(f"Approve error: {e}")
            return False
    
    @classmethod
    def block_user(cls, user_id, blocker_id, reason):
        if not cls._ok(): return False
        try:
            url = f"{cls.BASE}/rest/v1/users?id=eq.{user_id}"
            data = {
                'is_blocked': True, 
                'blocked_reason': reason, 
                'updated_at': datetime.now().isoformat()
            }
            r = requests.patch(url, headers=cls._h(), json=data)
            print(f"Block response: {r.status_code} - {r.text}")
            return r.status_code in [200, 201, 204]
        except Exception as e:
            print(f"Block error: {str(e)}")
            return False
    
    @classmethod
    def unblock_user(cls, user_id):
        if not cls._ok(): return False
        try:
            url = f"{cls.BASE}/rest/v1/users?id=eq.{user_id}"
            data = {
                'is_blocked': False, 
                'blocked_reason': None, 
                'updated_at': datetime.now().isoformat()
            }
            r = requests.patch(url, headers=cls._h(), json=data)
            print(f"Unblock response: {r.status_code} - {r.text}")
            return r.status_code in [200, 201, 204]
        except Exception as e:
            print(f"Unblock error: {str(e)}")
            return False
    
    @classmethod
    def delete_user(cls, user_id):
        if not cls._ok(): return False
        try:
            r = requests.delete(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'id': f'eq.{user_id}'})
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def update_last_login(cls, email):
        if not cls._ok(): return
        try:
            data = {'last_login': datetime.now().isoformat(), 'login_attempts': 0}
            r = requests.patch(f'{cls.BASE}/rest/v1/users', headers=cls._h(), params={'email': f'eq.{email}'}, json=data)
        except:
            pass
    
    # ========== TRANSACTIONS ==========
    @classmethod
    def get_tx(cls, d=None, cashier_id=None):
        if not cls._ok(): return []
        if not d: d = str(date.today())
        try:
            params = {'date': f'eq.{d}', 'order': 'created_at.desc'}
            if cashier_id:
                params['cashier_id'] = f'eq.{cashier_id}'
            r = requests.get(f'{cls.BASE}/rest/v1/transactions', headers=cls._h(), params=params)
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def save_tx(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/transactions', headers=cls._h(), json=data)
            if r.status_code in [200, 201]:
                res = r.json()
                result = res[0] if isinstance(res, list) else res
                cls._update_inventory(data.get('items', []))
                cls.log_audit(data.get('cashier_id'), 'sale', f"Sale: {data.get('total')}/=")
                return result
        except:
            pass
        return None
    
    @classmethod
    def del_tx(cls, tid):
        if not cls._ok(): return False
        try:
            r = requests.delete(f'{cls.BASE}/rest/v1/transactions', headers=cls._h(), params={'id': f'eq.{tid}'})
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def _update_inventory(cls, items):
        if isinstance(items, str):
            items = json.loads(items)
        for item in items:
            name = item.get('name', '').lower()
            qty = item.get('qty', 1)
            try:
                r = requests.get(f'{cls.BASE}/rest/v1/inventory', headers=cls._h(), params={'item_name': f'ilike.%{name.split()[0]}%', 'limit': '1'})
                data = r.json()
                if data:
                    current = data[0]
                    new_qty = max(0, current['quantity'] - qty)
                    requests.patch(f'{cls.BASE}/rest/v1/inventory', headers=cls._h(), params={'id': f'eq.{current["id"]}'}, json={'quantity': new_qty, 'updated_at': datetime.now().isoformat()})
            except:
                pass
    
    # ========== EXPENSES ==========
    @classmethod
    def get_exp(cls, d=None):
        if not cls._ok(): return []
        if not d: d = str(date.today())
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/expenses', headers=cls._h(), params={'date': f'eq.{d}', 'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def save_exp(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/expenses', headers=cls._h(), json=data)
            if r.status_code in [200, 201]:
                res = r.json()
                cls.log_audit(data.get('created_by'), 'expense', f"Expense: {data.get('name')} {data.get('amount')}/=")
                return res[0] if isinstance(res, list) else res
        except:
            pass
        return None
    
    @classmethod
    def del_exp(cls, eid):
        if not cls._ok(): return False
        try:
            r = requests.delete(f'{cls.BASE}/rest/v1/expenses', headers=cls._h(), params={'id': f'eq.{eid}'})
            return r.status_code in [200, 204]
        except:
            return False
    
    # ========== INVENTORY ==========
    @classmethod
    def get_inventory(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/inventory', headers=cls._h(), params={'order': 'category.asc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def update_inventory_item(cls, item_id, data):
        if not cls._ok(): return False
        try:
            data['updated_at'] = datetime.now().isoformat()
            r = requests.patch(f'{cls.BASE}/rest/v1/inventory', headers=cls._h(), params={'id': f'eq.{item_id}'}, json=data)
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def add_inventory_item(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/inventory', headers=cls._h(), json=data)
            return r.json() if r.status_code in [200, 201] else None
        except:
            return None
    
    # ========== AUDIT LOGS ==========
    @classmethod
    def log_audit(cls, user_id, action, details):
        if not cls._ok(): return
        try:
            data = {'user_id': user_id, 'action': action, 'details': details, 'created_at': datetime.now().isoformat()}
            requests.post(f'{cls.BASE}/rest/v1/audit_logs', headers=cls._h(), json=data, timeout=5)
        except Exception as e:
            print(f"Audit log error: {e}")
    
    @classmethod
    def get_audit_logs(cls, limit=100):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/audit_logs', headers=cls._h(), params={'order': 'created_at.desc', 'limit': str(limit)})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    # ========== TRASH ==========
    @classmethod
    def get_trash(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/trash', headers=cls._h(), params={'order': 'trashed_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def save_trash(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/trash', headers=cls._h(), json=data)
            return r.json() if r.status_code in [200, 201] else None
        except:
            return None
    
    @classmethod
    def del_trash(cls, tid):
        if not cls._ok(): return False
        try:
            r = requests.delete(f'{cls.BASE}/rest/v1/trash', headers=cls._h(), params={'id': f'eq.{tid}'})
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def empty_trash(cls):
        if not cls._ok(): return False
        try:
            r = requests.delete(f'{cls.BASE}/rest/v1/trash', headers=cls._h(), params={'id': 'gt.0'})
            return r.status_code in [200, 204]
        except:
            return False
    
    # ========== SUMMARY ==========
    @classmethod
    def summary(cls, d=None):
        if not d: d = str(date.today())
        tx = cls.get_tx(d)
        ex = cls.get_exp(d)
        return {
            'total_sales': sum(t.get('total', 0) for t in tx),
            'total_expenses': sum(e.get('amount', 0) for e in ex),
            'transaction_count': len(tx),
            'expense_count': len(ex)
        }
    
    # ========== CREDIT ==========
    @classmethod
    def get_credit_sales(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/credit_sales', headers=cls._h(), params={'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def save_credit(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/credit_sales', headers=cls._h(), json=data)
            if r.status_code in [200, 201]:
                res = r.json()
                return res[0] if isinstance(res, list) else res
        except:
            pass
        return None
    
    @classmethod
    def update_credit(cls, credit_id, data):
        if not cls._ok(): return False
        try:
            r = requests.patch(f'{cls.BASE}/rest/v1/credit_sales', headers=cls._h(), params={'id': f'eq.{credit_id}'}, json=data)
            return r.status_code in [200, 204]
        except:
            return False
    
    # ========== STOCK ==========
    @classmethod
    def get_stock(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/stock', headers=cls._h(), params={'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def get_stock_by_id(cls, stock_id):
        if not cls._ok(): return None
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/stock', headers=cls._h(), params={'id': f'eq.{stock_id}', 'limit': '1'})
            data = r.json()
            return data[0] if data else None
        except:
            return None
    
    @classmethod
    def save_stock(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/stock', headers=cls._h(), json=data)
            if r.status_code in [200, 201]:
                res = r.json()
                return res[0] if isinstance(res, list) else res
        except:
            pass
        return None
    
    @classmethod
    def update_stock(cls, stock_id, data):
        if not cls._ok(): return False
        try:
            r = requests.patch(f'{cls.BASE}/rest/v1/stock', headers=cls._h(), params={'id': f'eq.{stock_id}'}, json=data)
            return r.status_code in [200, 204]
        except:
            return False
    
    @classmethod
    def save_stock_usage(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/stock_usage', headers=cls._h(), json=data)
            return r.json() if r.status_code in [200, 201] else None
        except:
            return None
    
    # ========== SODA ==========
    @classmethod
    def get_soda_inventory(cls):
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/soda_inventory', headers=cls._h(), params={'order': 'created_at.desc'})
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    @classmethod
    def save_soda(cls, data):
        if not cls._ok(): return None
        try:
            r = requests.post(f'{cls.BASE}/rest/v1/soda_inventory', headers=cls._h(), json=data)
            if r.status_code in [200, 201]:
                res = r.json()
                return res[0] if isinstance(res, list) else res
        except:
            pass
        return None
    
    @classmethod
    def get_all_tx(cls):
        """Get ALL transactions (not just today)"""
        if not cls._ok(): return []
        try:
            r = requests.get(f'{cls.BASE}/rest/v1/transactions', 
                           headers=cls._h(), 
                           params={'order': 'created_at.desc', 'limit': '500'})
            return r.json() if r.status_code == 200 else []
        except:
            return []