"""Verified DX11 instance date field, for the current UTC+8 local deployment.

1988B10 parses local wall time and expires only when server seconds > deadline.
Other client time zones must be verified before deploying this encoding there.
"""
from datetime import datetime,timedelta,timezone
import time

CLIENT_ZONE=timezone(timedelta(hours=8))
MINIMUM=int(datetime(1971,1,1,tzinfo=CLIENT_ZONE).timestamp())
MAXIMUM=int(datetime(2999,12,31,23,59,59,tzinfo=CLIENT_ZONE).timestamp())


def validate(value):
    if type(value) is not int or not MINIMUM<=value<=MAXIMUM:
        raise ValueError('Invalid item expiration epoch')
    return value


def date_string(value):
    return datetime.fromtimestamp(validate(value),CLIENT_ZONE).strftime('%Y-%m-%d %H:%M:%S')


def expired(item,*,now=None):
    if 'expires_at' not in item:return False
    now=int(time.time()) if now is None else now
    if type(now) is not int or now<0:raise ValueError('Invalid expiration clock')
    return now>validate(item['expires_at'])


def require_current(item,*,now=None):
    """Recheck at the transaction boundary, independent of the periodic sweep."""
    if expired(item,now=now):raise ValueError('Item has expired')
