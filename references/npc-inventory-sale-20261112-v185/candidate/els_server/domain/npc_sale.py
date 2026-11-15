"""NPC resale using original 198A700 float math.

Ice avatars require the original positive ED price and resale class.
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
    flags = row['flags4']
    base_ed, base_vp = struct.unpack_from('<ii', row['record'], 0x1c)
    native_resale = flags & 0xf0000000 == 0x20000000
    # ST_ICE_HEATER_AVATAR has its own native tab and sets the cosmetic bit.
    ice_avatar = (for_merchant_sale and item['group'] == 27 and row['item_type'] in (1, 2, 3)
                  and native_resale and flags & 0xa1 == 1 and base_ed > 0)
    # The native Life tab uses ST_LIFE (21). Its direct-sale controller
    # selects trade class 2 (template+4, high nibble).
    life_item = for_merchant_sale and item['group'] == 21 and row['item_type'] == 15 and native_resale
    if item['group'] not in (1, 2, 3, 4, 5, 6) and not (life_item or ice_avatar):
        raise ValueError('Sellable bag item required for merchant sale')
    if flags & 0xa1 and not ice_avatar:
        raise ValueError('Special merchant permissions not recovered')
    durable = flags & 0xf000000 == 0x1000000
    ratio = f32(1)
    if durable:
        from els_server.domain.equipment_durability import LEGACY_INITIAL_DURABILITY, maximum
        if not for_merchant_sale and item['template'] in LEGACY_INITIAL_DURABILITY:
            raise ValueError('Unverified durability equipment')
        cap = maximum(item['template'])
        ratio = f32(f32(item.get('durability', 0))/f32(cap))
    value = f32(f32(f32(base_ed)*f32(.2))*ratio)
    if base_ed < 0 or not math.isfinite(value) or not 0 <= value < 2**31:
        raise ValueError('Item has no positive native merchant value')
    price = math.trunc(value)
    # The original bag sale selects trade class 2 and can submit for zero ED.
    # A zero base price does not depend on wear. A positive base price does.
    if price == 0 and not (
        for_merchant_sale and native_resale
        and (base_ed != 0 or base_vp == 0)
        and (base_ed == 0 or not durable or 'durability' in item)
    ):
        raise ValueError('Item has no positive native merchant value')
    return price
