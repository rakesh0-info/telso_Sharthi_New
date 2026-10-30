from datetime import datetime, timedelta
import random 
def generate_otp():
    return str(random.randint(100000, 999999))


def get_otp_expiry(minutes: int = 10) -> datetime:
    """Returns a UTC expiration time matching the current database columns."""
    return datetime.utcnow() + timedelta(minutes=minutes)