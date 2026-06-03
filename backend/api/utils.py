from datetime import datetime, timedelta

def get_business_day():
    """Business day starts at 0930 and ends at 0930 next day."""
    now = datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def get_current_shift():
    """Returns 'day' or 'night' based on current time"""
    now = datetime.now()
    total_min = now.hour * 60 + now.minute
    if total_min >= 570 and total_min < 1320:
        return 'day'
    return 'night'