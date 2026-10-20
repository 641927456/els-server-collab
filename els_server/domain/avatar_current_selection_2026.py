"""Avatar portion of the native current equipment registration gate.

Original 2239F10 registers group9 through 85CDB0 -> 85CE30. Before admission,
85E0F0/868240 require identified items and the original wear restriction.
Pinned avatar templates all have required level zero, nonzero equip flags,
and no non-fashion armor-name exception. Preset-switch protocol is separate.
"""
import hashlib
import json

SOURCE_SHA256 = 'a5be767193bdec7282902adc2109bd3b18eaa0d88c8255e63209223a399dc6d6'


def load_original_metadata(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned current equipment metadata required')
    return {row[0]: tuple(row[1:]) for row in json.loads(raw)['rows']}


def current_avatar_uids(*, items, unit_type, unit_class, metadata, admission_policy):
    """items must come from load_items for one owner in the caller transaction.

    Existing inventory validation enforces original bag/slot correspondence,
    one item per equipped slot and no unverified appearance override fields.
    This does not turn bag contents or an inactive preset into worn items.
    """
    if type(unit_type) is not int or unit_type <= 0 or type(unit_class) is not int:
        raise ValueError('Authoritative character identity required')
    classes = admission_policy[1]
    if unit_class not in classes:
        raise ValueError('Unresolved character class')
    result = []
    for item in items:
        template = item['template']
        if item['group'] != 9 or template not in metadata:
            continue
        identified = item.get('identified', True)
        if type(identified) is not bool:
            raise ValueError('Unresolved identification state')
        if not identified:
            continue
        mode, required_unit, required_class, position = metadata[template]
        if mode == 2 and unit_type != required_unit:
            continue
        if mode == 3:
            family, branch, stage = classes[unit_class]
            rf, rb, rs = classes[required_class]
            if family != rf or (rb and branch != rb) or stage < rs:
                continue
        result.append(item['uid'])
    return tuple(result)
