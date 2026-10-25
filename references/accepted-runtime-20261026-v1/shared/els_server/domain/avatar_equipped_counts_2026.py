"""Original avatar-set counting after the native equipment admission stage.

The caller supplies ordered, admitted equipment instances. This module cannot
turn inventory ownership into equipment admission; 8A20E0 and its predicates
must be implemented by that caller. No database or quest writes occur here.
"""
import hashlib
import json

SOURCE_SHA256 = 'dc7951ca6bac97c1258c9d34c1c6ddb99d7ff19938ce22ce888d159d309163dc'


def load_original_membership(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned original item membership required')
    rows = json.loads(raw)['rows']
    result = {row['template']: (row['set_id'], row['selector'], row['flag7']) for row in rows}
    if len(result) != 11176:
        raise ValueError('Original item membership coverage changed')
    return result


def count_admitted(*, instances, selected, context2912, side, membership,
                   selector_overrides, include_flag7):
    """instances: tuple of (unique instance UID, original template ID).

    Selector overrides are authoritative (set ID, side) -> selector entries
    from the caller-selected state map, not values supplied by the packet.
    Only the recovered avatar-set branch is covered.
    """
    if type(context2912) is not int or not 0 <= context2912 <= 65535:
        raise ValueError('Explicit character context required')
    if type(side) is not int or side not in (0, 1) or type(include_flag7) is not bool:
        raise ValueError('Explicit side and flag policy required')
    if type(instances) is not tuple or type(selected) is not tuple or type(membership) is not dict or type(selector_overrides) is not dict:
        raise ValueError('Explicit authoritative inputs required')
    for row in selected:
        if type(row) is not tuple or len(row) != 4 or any(type(x) is not int or not -2**31 <= x < 2**31 for x in row):
            raise ValueError('Invalid saved selection record')
    for key, value in selector_overrides.items():
        if type(key) is not tuple or len(key) != 2 or any(type(x) is not int for x in key) or key[0] <= 0 or key[1] not in (0, 1) or type(value) is not int or not 0 <= value < 2**31:
            raise ValueError('Invalid authoritative selector override')
    # Original 867440 checks context and set here; side is filtered later
    # by 198A0A0. Do not silently conflate these two stages.
    selected_ids = {row[3] for row in selected if row[0] == context2912}
    seen = set()
    counts = {}
    for instance in instances:
        if type(instance) is not tuple or len(instance) != 2 or any(type(x) is not int or x <= 0 for x in instance):
            raise ValueError('Invalid admitted instance')
        uid, template = instance
        if uid in seen:
            raise ValueError('Repeated equipment instance')
        seen.add(uid)
        if template not in membership:
            raise ValueError('Unresolved or non-avatar item outside this branch')
        set_id, selector, flag7 = membership[template]
        if set_id not in selected_ids or (flag7 and not include_flag7):
            continue
        if set_id in counts:
            previous, count = counts[set_id]
            counts[set_id] = (previous, count + 1)
        else:
            counts[set_id] = (selector_overrides.get((set_id, side), selector), 1)
    return counts
