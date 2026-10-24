"""GM-only accessory admission derived from the pinned client item record.

The verified inventory catalog covers most accessories; the remaining ones
share the same record layout. Placement is derived the same way the native
fashion catalog does it: flags8 bit 0x100 selects the costume bag (27),
otherwise 7, and ordinary accessory slots use bag 2.
"""
import functools
import struct

ACCESSORY_POSITIONS = frozenset(range(15, 29)) | frozenset(range(48, 60))


@functools.lru_cache(maxsize=1)
def circuit_templates():
    """Circuit policy records plus the T/I/L amplification circuit items."""
    from els_server.domain.equipment_circuit_rules import catalog as circuit_catalog
    from els_server.game_data import client_data
    record = circuit_catalog()
    result = {int(key) for key in record['materials']} | {int(key) for key in record['targets']}
    with client_data().connect() as db:
        result.update(row[0] for row in db.execute(
            "SELECT id FROM items WHERE name LIKE '%增幅电路%' AND item_type IN (1,2,3)"))
    return frozenset(result)



def _group(item):
    position = item['equip_position']
    flags4, flags8 = struct.unpack_from('<II', item['record'], 4)
    if position < 48:
        return 4 if flags4 & 0x40000000 else 2
    return 27 if flags8 & 256 else 7


def entries():
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES
    from els_server.game_data import client_data
    data = client_data()
    positions = sorted(ACCESSORY_POSITIONS)
    with data.connect() as db:
        identities = [row[0] for row in db.execute(
            'SELECT id FROM items WHERE equip_position IN (' + ','.join('?' * len(positions)) + ') ORDER BY id',
            positions)]
    for template in identities:
        if template in VERIFIED_TEMPLATES:
            continue
        item = data.item(template)
        yield dict(id=template, name=item['name'], group=_group(item), stack=1,
                   metadata=item['metadata'])
    for template in sorted(circuit_templates()):
        if template in VERIFIED_TEMPLATES:
            continue
        item = data.item(template)
        yield dict(id=template, name=item['name'], group=1, stack=1,
                   metadata=item['metadata'])


def _circuit_plan(template, quantity):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
    from els_server.game_data import client_data
    item = client_data().item(template)
    VERIFIED_TEMPLATES[template] = item['metadata']
    TEMPLATE_BAG_GROUPS[template] = 1
    TEMPLATE_MAX_STACKS[template] = 1
    return dict(template=template, quantity=quantity, metadata=item['metadata'], group=1)


def plan(template, quantity):
    from els_server.domain.inventory_items import (VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS,
        TEMPLATE_MAX_STACKS, FASHION_EQUIP_SLOTS, FASHION_POSITIONS)
    from els_server.domain.reward_rules import item_plan
    if template in VERIFIED_TEMPLATES:
        return item_plan(template, quantity)
    if type(template) is not int or type(quantity) is not int or not 1 <= quantity <= 99:
        raise ValueError('Reward quantity bound')
    from els_server.game_data import client_data
    item = client_data().item(template)
    if item['equip_position'] not in ACCESSORY_POSITIONS:
        if template in circuit_templates():
            return _circuit_plan(template, quantity)
        raise ValueError('该道具尚未在当前服务端验证，不能发放')
    group = _group(item)
    metadata = item['metadata']
    VERIFIED_TEMPLATES[template] = metadata
    TEMPLATE_BAG_GROUPS[template] = group
    TEMPLATE_MAX_STACKS[template] = 1
    if item['equip_position'] in FASHION_POSITIONS:
        FASHION_EQUIP_SLOTS[template] = FASHION_POSITIONS[item['equip_position']]
    return dict(template=template, quantity=quantity, metadata=metadata, group=group)
