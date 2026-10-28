"""8A3D6F..8A3EC2 group22 template-option tail, before Unit2988.

This is separate from the fishing entries already present in DTO equipment.
Only the original template options are appended here, by inventory slot. No
class/side selection, item identification or bait options are added by this
loop. Capacity is supplied by the qualified Unit/inventory producer.
"""
from els_server.domain.native_worn_item_inputs import valid


def option_ids(items, bound, records, *, capacity, category77, special_mode_level):
    if type(items) is not tuple or type(capacity) is not int or not 0 <= capacity <= 65535:
        raise ValueError('Complete owned fishing items and original capacity required')
    rows = [item for item in items if item['group'] == 22]
    if len({item['slot']for item in rows}) != len(rows):
        raise ValueError('Duplicate original fishing inventory slot')
    result = []
    from els_server.domain.native_set_sources import item_pools
    for item in sorted(rows, key=lambda row: row['slot']):
        slot = item['slot']
        if type(slot) is not int or slot < 0:
            raise ValueError('Original nonnegative fishing inventory slot required')
        if slot >= capacity:
            continue
        row = bound[item['uid']]
        if not valid(row, feature77=category77[row['template_id']],
                     special_mode_level=special_mode_level):
            continue
        result.extend(item_pools(records[item['uid']])[1])
    return tuple(result)
