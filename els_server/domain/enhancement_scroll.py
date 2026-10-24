"""Owner-requested local +13 enhancement scrolls, pinned to client records.

These scrolls are consumables that target one equipment instance. The record
identity and the equip kind are fixed here; the actual use is transactional in
els_server.storage.enhancement_scroll.
"""
import functools
import hashlib

from els_server.game_data import client_data

TARGET_LEVEL = 13  # Legacy Lv.13 default retained for callers that still ask.
# Only one generic scroll per level is registered; the variants stay unadmitted.
SCROLLS = {
    163313: ('any', '50221809d748920d2a1dc4f7d54073642ef9e63e0117e8968f01f562933fe01a', 13, 1),
    117535: ('any', 'f9707e4a03d6de2db7198e7af83bd9b7a816280eae5267eb23d2c0ef8d80a718', 12, 1),
    117534: ('any', 'f8006f421a19f6f2d8ad34e087f767464cae6fe4a37fc1d620132cc4439c54fa', 11, 1),
    130152: ('any', '3cf9be687defb69b8f7f58932c5b936774a6d2018aacba951058db6bada73df1', 10, 999),
    130150: ('any', '6e31801f9cf07a5539539dea00b090b357a595b25562f9e9c18e7ae6805608fc', 8, 999),
    130149: ('any', 'b1e4da5f8ba0677244f8483a56ae517cd16a2c73696945667a0870b4ac86acfd', 7, 999),
}


@functools.lru_cache(maxsize=1)
def definitions():
    result = {}
    for template, (kind, digest, level, max_stack) in SCROLLS.items():
        item = client_data().item(template)
        record = item['record']
        if (item['item_type'] != 7 or '强化卷轴' not in item['name']
                or 'Lv.'+str(level) not in item['name']
                or hashlib.sha256(record).hexdigest() != digest):
            raise ValueError('Enhancement scroll record changed: '+str(template))
        # Bag group follows the verified enhancement coupon family (130149-130152).
        result[template] = dict(template=template, kind=kind, level=level,
                                metadata=record[7] & 15, group=4, max_stack=max_stack)
    return result


def scroll(template):
    return template in SCROLLS


def defs_for_display():
    return definitions()


def kind(template):
    return SCROLLS[template][0]


def level(template):
    return SCROLLS[template][2]
