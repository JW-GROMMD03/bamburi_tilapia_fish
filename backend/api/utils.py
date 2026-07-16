from datetime import datetime, timedelta

def get_business_day():
    """Business day starts at 09:30. Returns date string."""
    now = datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def get_current_shift():
    """Returns current shift based on time."""
    now = datetime.now()
    hour = now.hour
    if hour >= 22 or hour < 9:
        return 'night'
    return 'day'