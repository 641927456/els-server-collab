"""Owned SQL inventory to avatar admission, with explicit current selection.

This is a candidate adapter, not a preset selector or packet handler. The
caller must resolve current equipment UIDs and authoritative category77 / owner
context before calling. No guessed default for either restriction is allowed.
"""
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.domain.item_expiration import require_current
from els_server.domain.avatar_equipment_admission_2026 import EquipmentState, admit_current


def snapshot(db, *, owner, current_uids, side, category77, owner_7bd, policy, now):
    if not db.in_transaction:
        raise ValueError('Equipment snapshot requires caller transaction')
    owner = character_uid(owner)
    if type(current_uids) is not tuple or any(type(x) is not int or not 0 < x < 2**63 for x in current_uids):
        raise ValueError('Authoritative current equipment selection required')
    if len(set(current_uids)) != len(current_uids):
        raise ValueError('Repeated current equipment UID')
    if type(category77) is not dict or type(owner_7bd) is not bool:
        raise ValueError('Explicit authoritative restriction state required')
    if type(now) is not int or now < 0:
        raise ValueError('Explicit transaction clock required')
    row = db.execute('SELECT unit_class FROM characters WHERE uid=?', (owner,)).fetchone()
    if row is None:
        raise ValueError('Unknown equipment owner')
    items = {item['uid']: item for item in load_items(db, owner)}
    states = []
    for uid in current_uids:
        item = items.get(uid)
        if item is None or item['group'] != 9 or item['count'] != 1:
            raise ValueError('Selection must be owned and actually equipped')
        require_current(item, now=now)
        template = item['template']
        if template not in category77 or type(category77[template]) is not bool:
            raise ValueError('Unresolved original category77 membership')
        # 197E220 copies group/slot into wrapper+0/+4. 7EB0D0 copies
        # metadata, durability and enhancement into item+0C/+10/+18.
        # Missing durability/enhancement encode as zero in existing item_body.
        states.append(EquipmentState(uid, template, item['group'], item['slot'],
                                     item['metadata'], item.get('durability', 0),
                                     item.get('enhancement', 0), category77[template], owner_7bd))
    states = tuple(states)
    admitted = admit_current(selected_uids=current_uids, equipment=states,
                             class_id=row[0], side=side, policy=policy)
    return states, admitted
