"""Original item readers for anniversary wardrobe and bag-expansion bundles."""
import hashlib
import json
import struct

from els_server.domain.bag_capacity import PRODUCT_GROUPS
from els_server.game_data import client_data

CAPACITY_BOX = 154169
TRANSPARENT_BOX = 720959
BOXES = frozenset((CAPACITY_BOX, TRANSPARENT_BOX))
ACCESSORIES = frozenset((*range(185151, 185158), *range(394957, 394961)))
CAPACITY_PRODUCTS = {**dict(zip(range(154170, 154176), range(200751, 200757))), 135965: 135964}
ONEPIECE = {
    1: 190321, 2: 190322, 3: 190323, 4: 190324, 5: 190325,
    6: 190326, 7: 190327, 8: 190328, 9: 190329, 10: 190330,
    11: 190332, 12: 190334, 13: 190740, 14: 191103, 15: 191128,
}
CIEL_ONEPIECE = 190331
BUNDLE_OUTPUTS = frozenset((*CAPACITY_PRODUCTS, *ONEPIECE.values(), CIEL_ONEPIECE))
DIRECT_OUTPUTS = BOXES | ACCESSORIES
DEFINITION_SHA = hashlib.sha256(json.dumps(
    [CAPACITY_BOX, TRANSPARENT_BOX, CAPACITY_PRODUCTS, ONEPIECE, CIEL_ONEPIECE], sort_keys=True
).encode()).hexdigest()


def capacity_tickets():
    return {template: dict(capacity_group=PRODUCT_GROUPS[product], canonical_product=product)
            for template, product in CAPACITY_PRODUCTS.items()}


def definitions():
    client = client_data()
    for template in sorted(DIRECT_OUTPUTS | BUNDLE_OUTPUTS):
        item = client.item(template)
        raw = item['record']
        stack = struct.unpack_from('<I', raw, 16)[0]
        if template in BOXES:
            if (item['metadata'], item['item_type'], stack) != (0, 7, 0):
                raise ValueError('Anniversary bundle native identity')
            yield dict(template=template, metadata=0, group=4, max_stack=1)
        elif template in CAPACITY_PRODUCTS:
            if (item['metadata'], item['item_type'], stack) != (2, 7, 300) or not item['name'].startswith('[路莉尔]背包扩张券'):
                raise ValueError('Anniversary bag coupon native identity')
            yield dict(template=template, metadata=2, group=4, max_stack=300)
        else:
            role = next((role for role, value in ONEPIECE.items() if value == template), 10 if template == CIEL_ONEPIECE else 0)
            if (item['metadata'], item['item_type'], stack, raw[210]) != (0, 2 if role else 3, 0, role):
                raise ValueError('Anniversary transparent fashion native identity')
            if not item['flags4'] & 1 or item['flags8'] & 256 or bool(item['flags8'] & 4) != (template == CIEL_ONEPIECE):
                raise ValueError('Anniversary transparent fashion slot identity')
            yield dict(template=template, metadata=0, group=7, max_stack=1, equip_position=item['equip_position'])


def outputs(box, unit_class, active):
    if box == CAPACITY_BOX:
        return tuple(dict(template=template, metadata=2, group=4, quantity=1) for template in CAPACITY_PRODUCTS)
    role = client_data().unit(unit_class)['unitType']
    template = CIEL_ONEPIECE if active == 1 else ONEPIECE[role]
    return (dict(template=template, metadata=0, group=7, quantity=1),)
