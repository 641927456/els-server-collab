"""Ordinary equipment/material resale, using original 198A700 float math.

Special/cash templates stay closed until their merchant permissions are known.
This is independent of the narrower dismantling reward eligibility rules.
"""
import math
import struct
from els_server.game_data import client_data
from els_server.domain.character_stats import f32
from els_server.domain.inventory_items import validate_item
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked


def unit_price(item):
    item = validate_item(item)
    require_current(item)
    require_unlocked(item)
    if item['group'] not in (1, 2, 3, 4, 5, 6):
        raise ValueError('Ordinary bag item required for merchant sale')
    row = client_data().item(item['template'])
    if row['flags4'] & 0xa1:
        raise ValueError('Special merchant permissions not recovered')
    raw = row['record']
    ratio = f32(1)
    if row['flags4'] & 0xf000000 == 0x1000000:
        from els_server.domain.equipment_durability import maximum
        cap = maximum(item['template'])
        ratio = f32(f32(item.get('durability', 0))/f32(cap))
    value = f32(f32(f32(struct.unpack_from('<i', raw, 0x1c)[0])*f32(.2))*ratio)
    # Reject the native float->signed-int overflow sentinel as well as templates
    # with no merchant value. Never turn a negative native value into income.
    if not math.isfinite(value) or not 0 < value < 2**31:
        raise ValueError('Item has no positive native merchant value')
    price = math.trunc(value)
    if price <= 0:
        raise ValueError('Item has no positive native merchant value')
    return price
