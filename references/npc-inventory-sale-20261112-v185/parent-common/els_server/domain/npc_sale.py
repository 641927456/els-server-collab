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


def unit_price(item, *, for_merchant_sale=False):
    item = validate_item(item)
    require_current(item)
    require_unlocked(item)
    row = client_data().item(item['template'])
    # The native Life tab uses ST_LIFE (21). Its direct-sale controller
    # selects trade class 2 (template+4, high nibble).
    if item['group'] not in (1, 2, 3, 4, 5, 6) and not (
        for_merchant_sale and item['group'] == 21 and row['item_type'] == 15
        and row['flags4'] & 0xf0000000 == 0x20000000
    ):
        raise ValueError('Sellable bag item required for merchant sale')
    if row['flags4'] & 0xa1:
        raise ValueError('Special merchant permissions not recovered')
    raw = row['record']
    ratio = f32(1)
    if row['flags4'] & 0xf000000 == 0x1000000:
        from els_server.domain.equipment_durability import LEGACY_INITIAL_DURABILITY, maximum
        if not for_merchant_sale and item['template'] in LEGACY_INITIAL_DURABILITY:
            raise ValueError('Unverified durability equipment')
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
