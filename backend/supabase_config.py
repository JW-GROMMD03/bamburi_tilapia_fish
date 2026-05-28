import os
from dotenv import load_dotenv

load_dotenv()

# We're using direct REST API calls now - no supabase client needed
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')

# For backward compatibility with views.py
supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    print(f"✅ Supabase configured: {SUPABASE_URL}")
else:
    print("⚠️ Supabase credentials not found in .env file")