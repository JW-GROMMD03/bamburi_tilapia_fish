# FishFlow Pro - Supabase Backend

## Setup

### 1. Supabase Setup
1. Create project at https://supabase.com
2. Run `supabase/schema.sql` in SQL Editor
3. Get your project URL and keys from Settings > API

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Supabase credentials
python manage.py migrate
python manage.py runserver