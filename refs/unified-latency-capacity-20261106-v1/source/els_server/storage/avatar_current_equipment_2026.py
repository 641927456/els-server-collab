"""Resolve currently worn avatar UIDs from existing owned inventory storage."""
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.avatar_equipment_2026 import snapshot
from els_server.domain.avatar_current_selection_2026 import current_avatar_uids


def snapshot_current(db, *, owner, side, category77, owner_7bd, policy, metadata, now):
    if not db.in_transaction:
        raise ValueError('Current equipment requires caller transaction')
    owner = character_uid(owner)
    identity = db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?', (owner,)).fetchone()
    if identity is None:
        raise ValueError('Unknown current equipment owner')
    current_uids = current_avatar_uids(items=load_items(db, owner), unit_type=identity[0],
                                      unit_class=identity[1], metadata=metadata, admission_policy=policy)
    return snapshot(db, owner=owner, current_uids=current_uids, side=side,
                    category77=category77, owner_7bd=owner_7bd, policy=policy, now=now)
