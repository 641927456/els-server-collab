"""Native instance +370/+50 lock deadline, distinct from item expiration."""
import time


def validate(value):
    if type(value) is not int or not 1 <= value < 2**63:
        raise ValueError('Invalid item lock deadline')
    return value


def locked(item, *, now=None):
    now = int(time.time()) if now is None else now
    return 'lock_until' in item and validate(item['lock_until']) >= now


def require_unlocked(item, *, now=None):
    stamp=int(time.time()) if now is None else now
    if locked(item, now=stamp):
        from els_server.gameplay_causes import failed_check
        failed_check('item_locked',dict(item_uid=item.get('uid'),template=item.get('template'),
            lock_until=item['lock_until'],evaluated_at=stamp))
        raise ValueError('Item is locked')


def settings():
    from els_server.game_data import client_data
    data = client_data()
    maximum, = data.rules('ItemManager.lua', 'g_pItemManager.SetItemLock_MaxDay')
    daily, = data.rules('ItemManager.lua', 'g_pItemManager.SetItemLock_EDPerDay')
    if (maximum, daily) != (30, 10000):
        raise ValueError('Unreviewed native item lock settings')
    return maximum, daily
