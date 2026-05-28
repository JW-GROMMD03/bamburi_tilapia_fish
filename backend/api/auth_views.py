from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from datetime import datetime
from .supabase_service import SupabaseAuth, SupabaseDB
import json
import requests


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    """Register a new user - auto-approves if created by admin/manager"""
    try:
        data = request.data
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip()
        phone = data.get('phone', '').strip()
        shift = data.get('shift', 'day')
        role = data.get('role', 'cashier')
        
        # CHECK IF THIS REQUEST COMES FROM AUTHENTICATED ADMIN/MANAGER
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        created_by_admin = False
        admin_profile = None
        
        if token and token != '':
            # Verify token and get admin user
            admin_user = SupabaseAuth.get_user(token)
            if admin_user:
                admin_profile = SupabaseDB.get_user_by_id(admin_user.get('id'))
                if admin_profile and admin_profile.get('role') in ['admin', 'manager']:
                    created_by_admin = True
                    print(f"✅ User being created by {admin_profile.get('role')}: {admin_profile.get('full_name')}")
        
        # Auto-approve if created by admin/manager
        is_approved = created_by_admin
        
        print(f"📝 Signup: {email} | Role: {role} | Shift: {shift} | Auto-approved: {is_approved}")
        
        # Validate required fields
        if not email or not password or not full_name:
            return Response({'error': 'Email, password, and full name are required'}, status=400)
        
        if len(password) < 8:
            return Response({'error': 'Password must be at least 8 characters'}, status=400)
        
        # Check if email already exists in users table
        existing_user = SupabaseDB.get_user_by_email(email)
        if existing_user:
            # Check if this user exists in Supabase Auth
            user_id = existing_user.get('id')
            # Try to get user from auth to see if they have an auth record
            try:
                auth_url = f"{SupabaseAuth.URL}/auth/v1/admin/users/{user_id}"
                auth_headers = {
                    'apikey': SupabaseAuth.SERVICE_KEY,
                    'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}'
                }
                auth_check = requests.get(auth_url, headers=auth_headers, timeout=10)
                if auth_check.status_code == 200:
                    # User exists in auth too
                    return Response({'error': 'An account with this email already exists'}, status=409)
                else:
                    # User exists in table but not in auth - delete from table and recreate
                    print(f"⚠️ User {email} exists in table but not in auth. Recreating...")
                    SupabaseDB.delete_user(user_id)
            except Exception as e:
                print(f"⚠️ Auth check error: {str(e)}")
        
        # ALWAYS CREATE USING ADMIN API FIRST (most reliable)
        try:
            admin_url = f"{SupabaseAuth.URL}/auth/v1/admin/users"
            admin_headers = {
                'apikey': SupabaseAuth.SERVICE_KEY,
                'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}',
                'Content-Type': 'application/json'
            }
            admin_data = {
                'email': email,
                'password': password,
                'email_confirm': True,
                'user_metadata': {
                    'full_name': full_name,
                    'phone': phone,
                    'role': role,
                    'shift': shift
                }
            }
            
            print(f"🔗 Creating user via Admin API...")
            admin_r = requests.post(admin_url, headers=admin_headers, json=admin_data, timeout=15)
            print(f"📡 Admin API response: {admin_r.status_code}")
            
            if admin_r.status_code in [200, 201]:
                auth_user = admin_r.json()
                user_id = auth_user.get('id')
                print(f"✅ Auth user created: {user_id}")
                
                user_profile = {
                    'id': user_id,
                    'full_name': full_name,
                    'email': email,
                    'phone': phone,
                    'role': role,
                    'shift': shift,
                    'is_approved': is_approved,
                    'is_blocked': False,
                    'created_at': datetime.now().isoformat()
                }
                
                profile_url = f"{SupabaseAuth.URL}/rest/v1/users"
                profile_headers = {
                    'apikey': SupabaseAuth.SERVICE_KEY,
                    'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}',
                    'Content-Type': 'application/json',
                    'Prefer': 'return=representation'
                }
                
                # Check if user already exists in table (cleanup from earlier)
                check_url = f"{SupabaseAuth.URL}/rest/v1/users?id=eq.{user_id}"
                check_r = requests.get(check_url, headers=profile_headers, timeout=10)
                if check_r.status_code == 200 and check_r.json():
                    # Update existing
                    requests.patch(profile_url, headers=profile_headers, params={'id': f'eq.{user_id}'}, json=user_profile, timeout=15)
                else:
                    # Insert new
                    profile_r = requests.post(profile_url, headers=profile_headers, json=user_profile, timeout=15)
                    print(f"📋 Profile creation: {profile_r.status_code}")
                
                message = 'Account created and approved successfully!' if is_approved else 'Account created. Waiting for admin approval.'
                
                return Response({
                    'message': message,
                    'is_approved': is_approved,
                    'user': {'id': user_id, 'email': email, 'full_name': full_name, 'role': role}
                }, status=201)
            else:
                error_detail = admin_r.text[:200] if admin_r.text else 'Unknown error'
                print(f"⚠️ Admin API failed: {admin_r.status_code} - {error_detail}")
                
                # Try to get more specific error
                if admin_r.status_code == 422:
                    return Response({'error': 'Invalid email format or password too weak. Use at least 8 characters.'}, status=400)
                elif admin_r.status_code == 409:
                    return Response({'error': 'Email already exists in authentication system. Please use a different email.'}, status=409)
                    
        except Exception as e:
            print(f"⚠️ Admin API exception: {str(e)}")
        
        # FALLBACK: Try public signup
        try:
            pub_url = f"{SupabaseAuth.URL}/auth/v1/signup"
            pub_headers = {
                'apikey': SupabaseAuth.KEY,
                'Content-Type': 'application/json'
            }
            pub_data = {
                'email': email,
                'password': password,
                'data': {
                    'full_name': full_name,
                    'phone': phone,
                    'role': role,
                    'shift': shift
                }
            }
            
            print(f"🔗 Trying public signup...")
            pub_r = requests.post(pub_url, headers=pub_headers, json=pub_data, timeout=15)
            print(f"📡 Public signup response: {pub_r.status_code}")
            
            if pub_r.status_code in [200, 201]:
                pub_user = pub_r.json()
                user_id = pub_user.get('user', {}).get('id') or pub_user.get('id')
                
                if user_id:
                    # Insert into users table
                    user_profile = {
                        'id': user_id,
                        'full_name': full_name,
                        'email': email,
                        'phone': phone,
                        'role': role,
                        'shift': shift,
                        'is_approved': is_approved,
                        'is_blocked': False,
                        'created_at': datetime.now().isoformat()
                    }
                    
                    profile_url = f"{SupabaseAuth.URL}/rest/v1/users"
                    profile_headers = {
                        'apikey': SupabaseAuth.SERVICE_KEY,
                        'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}',
                        'Content-Type': 'application/json',
                        'Prefer': 'return=representation'
                    }
                    
                    requests.post(profile_url, headers=profile_headers, json=user_profile, timeout=15)
                    
                    message = 'Account created and approved successfully!' if is_approved else 'Account created. Waiting for admin approval.'
                    
                    return Response({
                        'message': message,
                        'is_approved': is_approved,
                        'user': {'id': user_id, 'email': email, 'full_name': full_name, 'role': role}
                    }, status=201)
            else:
                error_detail = pub_r.text[:200] if pub_r.text else 'Unknown error'
                print(f"⚠️ Public signup failed: {pub_r.status_code} - {error_detail}")
                
                if pub_r.status_code == 422:
                    return Response({'error': 'Weak password. Use at least 8 characters with letters and numbers.'}, status=400)
                    
        except Exception as e:
            print(f"⚠️ Public signup exception: {str(e)}")
        return Response({'error': 'Failed to create account. Please check your internet connection and try again.'}, status=400)
        
    except Exception as e:
        print(f"❌ Signup exception: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """Login user - uses Supabase Auth directly"""
    try:
        data = request.data
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        print(f"🔑 Login attempt: {email}")
        
        if not email or not password:
            return Response({'error': 'Email and password required'}, status=400)
        
        # Try Supabase Auth login directly
        login_url = f"{SupabaseAuth.URL}/auth/v1/token?grant_type=password"
        login_headers = {
            'apikey': SupabaseAuth.KEY,
            'Content-Type': 'application/json'
        }
        login_data = {
            'email': email,
            'password': password
        }
        
        print(f"🔗 Calling Supabase Auth...")
        login_r = requests.post(login_url, headers=login_headers, json=login_data, timeout=10)
        print(f"📡 Login response: {login_r.status_code}")
        
        if login_r.status_code == 200:
            token_data = login_r.json()
            
            # Get user profile from users table
            user_data = SupabaseDB.get_user_by_email(email)
            
            if user_data:
                # Check if blocked
                if user_data.get('is_blocked'):
                    return Response({
                        'error': 'Your account has been blocked. Please contact admin.',
                        'blocked_reason': user_data.get('blocked_reason', '')
                    }, status=403)
                
                # Check if approved (skip for admin role)
                if user_data.get('role') != 'admin' and not user_data.get('is_approved'):
                    return Response({
                        'error': 'Your account is pending approval. Please wait for admin/manager approval.'
                    }, status=403)
                
                # Update last login
                SupabaseDB.update_last_login(email)
                
                return Response({
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'user': {
                        'id': user_data.get('id'),
                        'email': email,
                        'full_name': user_data.get('full_name', ''),
                        'role': user_data.get('role', 'cashier'),
                        'shift': user_data.get('shift', 'day'),
                        'is_approved': user_data.get('is_approved', False),
                        'is_blocked': user_data.get('is_blocked', False)
                    }
                })
            else:
                # User exists in auth but not in users table
                auth_user_info = token_data.get('user', {})
                user_id = auth_user_info.get('id')
                
                if user_id:
                    # Create missing profile
                    SupabaseDB.create_user_profile(user_id, {
                        'full_name': email.split('@')[0],
                        'email': email,
                        'phone': '',
                        'role': 'cashier',
                        'shift': 'day',
                        'is_approved': False,
                        'is_blocked': False
                    })
                
                return Response({
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'user': {
                        'id': user_id,
                        'email': email,
                        'full_name': email.split('@')[0],
                        'role': 'cashier',
                        'shift': 'day',
                        'is_approved': False,
                        'is_blocked': False
                    }
                })
        
        # Login failed
        error_msg = 'Invalid email or password'
        try:
            error_data = login_r.json()
            error_msg = error_data.get('error_description', error_data.get('msg', error_msg))
        except:
            pass
        
        print(f"❌ Login failed: {error_msg}")
        return Response({'error': error_msg}, status=401)
        
    except requests.exceptions.Timeout:
        print("⏰ Supabase timeout")
        return Response({'error': 'Login service temporarily unavailable. Please try again.'}, status=503)
    except requests.exceptions.ConnectionError:
        print("🔌 Supabase connection error")
        return Response({'error': 'Cannot connect to authentication service.'}, status=503)
    except Exception as e:
        print(f"❌ Login exception: {str(e)}")
        return Response({'error': 'Login failed. Please try again.'}, status=400)


@api_view(['GET'])
def get_profile(request):
    """Get current user profile"""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        # Get user from Supabase Auth
        user = SupabaseAuth.get_user(token)
        if user:
            profile = SupabaseDB.get_user_by_id(user['id'])
            if profile:
                return Response(profile)
            return Response(user)
        
        return Response({'error': 'Unauthorized'}, status=401)
    except Exception as e:
        return Response({'error': str(e)}, status=401)


@api_view(['GET'])
def get_cashiers(request):
    """Get all cashiers (for admin/manager)"""
    cashiers = SupabaseDB.get_all_cashiers()
    return Response(cashiers if cashiers else [])


@api_view(['GET'])
def get_managers(request):
    """Get all managers"""
    managers = SupabaseDB.get_all_managers()
    return Response(managers if managers else [])


@api_view(['POST'])
def approve_cashier(request, user_id):
    try:
        success = SupabaseDB.approve_user(user_id, None)
        if success:
            return Response({'message': 'User approved'}, status=200)
        return Response({'error': 'Failed'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=400)
    
@api_view(['POST'])
def reject_user(request, user_id):
    """Reject and permanently delete a user"""
    try:
        print(f"Rejecting user: {user_id}")
        # Delete from users table
        success = SupabaseDB.delete_user(user_id)
        if success:
            # Also try to delete from Supabase Auth
            try:
                url = f"{SupabaseAuth.URL}/auth/v1/admin/users/{user_id}"
                headers = {
                    'apikey': SupabaseAuth.SERVICE_KEY,
                    'Authorization': f'Bearer {SupabaseAuth.SERVICE_KEY}'
                }
                requests.delete(url, headers=headers, timeout=10)
            except:
                pass
            
            # Log the action
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '')
            admin_user = SupabaseAuth.get_user(token)
            if admin_user:
                SupabaseDB.log_audit(admin_user.get('id'), 'reject_user', f"Rejected and deleted user {user_id}")
            
            return Response({'message': 'User rejected and permanently deleted'}, status=200)
        return Response({'error': 'Failed to reject user'}, status=400)
    except Exception as e:
        print(f"Reject error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def block_user(request, user_id):
    """Block a user account"""
    try:
        reason = request.data.get('reason', 'Account blocked by admin')
        print(f"Blocking user: {user_id}, reason: {reason}")
        success = SupabaseDB.block_user(user_id, None, reason)
        if success:
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '')
            admin_user = SupabaseAuth.get_user(token)
            if admin_user:
                SupabaseDB.log_audit(admin_user.get('id'), 'block_user', f"Blocked user {user_id}: {reason}")
            return Response({'message': 'User blocked successfully'}, status=200)
        return Response({'error': 'Failed to block user'}, status=400)
    except Exception as e:
        print(f"Block error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def unblock_user(request, user_id):
    """Unblock a user account"""
    try:
        print(f"Unblocking user: {user_id}")
        success = SupabaseDB.unblock_user(user_id)
        if success:
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '')
            admin_user = SupabaseAuth.get_user(token)
            if admin_user:
                SupabaseDB.log_audit(admin_user.get('id'), 'unblock_user', f"Unblocked user {user_id}")
            return Response({'message': 'User unblocked successfully'}, status=200)
        return Response({'error': 'Failed to unblock user'}, status=400)
    except Exception as e:
        print(f"Unblock error: {str(e)}")
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
def reset_password(request, user_id):
    """Reset a user's password (admin/manager only)"""
    try:
        new_password = request.data.get('password')
        if not new_password or len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters'}, status=400)
        
        success = SupabaseAuth.reset_user_password(user_id, new_password)
        if success:
            # Log the action
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '')
            admin_user = SupabaseAuth.get_user(token)
            if admin_user:
                SupabaseDB.log_audit(admin_user.get('id'), 'reset_password', f"Reset password for user {user_id}")
            return Response({'message': 'Password reset successfully'}, status=200)
        return Response({'error': 'Failed to reset password'}, status=400)
    except Exception as e:
        print(f"Reset password error: {str(e)}")
        return Response({'error': str(e)}, status=400)