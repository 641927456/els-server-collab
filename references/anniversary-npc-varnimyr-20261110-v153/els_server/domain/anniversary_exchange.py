"""Deterministic anniversary coupons at the existing Ariel exchange menu."""
from functools import lru_cache
import json
from pathlib import Path
import struct

from els_server.domain.anniversary_promotion import ENDS, MAIL_DEADLINE, STARTS
from els_server.domain.anniversary_actions import books as action_books
from els_server.domain import magma_coupon

TOKEN = 100006360
ARIEL = 40017
SECONDS_PER_COUPON = 600
MAX_COUPONS = 20
MAIL_PREFIX = 'cn15-anniversary-coupon-'
RINGS = frozenset(range(710198, 710202))


@lru_cache(maxsize=1)
def prizes():
    data = json.loads((Path(__file__).resolve().parents[1] / 'data/anniversary_exchange.json').read_bytes())
    return {template: (count, limit, key, expires) for template, count, limit, key, expires in data}


def recipes(first_index):
    return [dict(index=index, house=ARIEL, type=3, source=TOKEN, destination=template, quantity=prize[0],
                 rate=100, source_quantity=1, period_days=0, category=3)
            for index, (template, prize) in enumerate(prizes().items(), first_index)]


def definitions():
    from els_server.game_data import client_data
    from els_server.domain.anniversary_extras import definitions as extras

    client = client_data()
    token = client.item(TOKEN)
    if token['item_type'] != 7 or token['metadata'] != 2 or struct.unpack_from('<I', token['record'], 16)[0] != 100:
        raise ValueError('Anniversary coupon native item')
    yield dict(template=TOKEN, metadata=2, group=4, max_stack=100)
    for template in sorted(RINGS):
        item = client.item(template)
        counterpart = client.item(template - 710198 + 183404)
        keys = ('item_type', 'metadata', 'flags4', 'flags8', 'equip_position', 'stats', 'stat_bonus')
        if any(item[key] != counterpart[key] for key in keys):
            raise ValueError('Anniversary skill ring native identity')
        yield dict(template=template, metadata=0, group=7, max_stack=1, equip_position=item['equip_position'])
    yield from extras()
    yield magma_coupon.definition()
    for template in action_books():
        yield dict(template=template, metadata=0, group=4, max_stack=1)


def exclusive_reward(template):
    from els_server.domain.anniversary_extras import DIRECT_OUTPUTS
    return template == magma_coupon.TEMPLATE or template in RINGS or template in DIRECT_OUTPUTS or template in action_books()


def deadline_for(template):
    return MAIL_DEADLINE if prizes()[template][3] else None


def reserve(db, account, template, quantity, now):
    if not STARTS <= now < ENDS:
        raise ValueError('Anniversary exchange is closed')
    _, limit, key, _ = prizes()[template]
    db.execute('''CREATE TABLE IF NOT EXISTS anniversary_exchange_uses (
        account INTEGER NOT NULL, prize TEXT NOT NULL, uses INTEGER NOT NULL,
        PRIMARY KEY(account, prize))''')
    row = db.execute('SELECT uses FROM anniversary_exchange_uses WHERE account=? AND prize=?', (account, key)).fetchone()
    uses = (row[0] if row is not None else 0) + quantity
    if uses > limit:
        raise ValueError('Anniversary account exchange limit')
    db.execute('''INSERT INTO anniversary_exchange_uses VALUES (?,?,?)
        ON CONFLICT(account, prize) DO UPDATE SET uses=excluded.uses''', (account, key, uses))
