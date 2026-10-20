"""Current-equipment branch of original 8A20E0, restricted to avatar sets.

Inputs are authoritative native-equivalent state, never client packet fields.
SQL fields and current-preset ownership are not inferred here. Raw item offsets
retain their names until their persistence mapping is independently recovered.
The preview branch with additional/excluded item pointers is outside this API.
"""
from dataclasses import dataclass
import hashlib
import json

POLICY_SHA256 = '84cc329f01aa3d01e88f96af31fecf50ace86764393997d3b1b6a0b5b5f75854'


def load_original_policy(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != POLICY_SHA256:
        raise ValueError('Pinned original admission policy required')
    data = json.loads(raw)
    return ({row[0]: tuple(row[1:]) for row in data['items']},
            {row[0]: tuple(row[1:]) for row in data['classes']},
            frozenset(data['slot_one']))


@dataclass(frozen=True)
class EquipmentState:
    uid: int
    template: int
    wrapper_type: int
    wrapper_slot: int
    item_0c: int
    item_10: int
    item_18: int
    category_4d: bool
    extension_7bd: bool | None


def admit_current(*, selected_uids, equipment, class_id, side, policy):
    """Return ordered (UID, template) instances for count_admitted.

    selected_uids is the current equipment vector, not all owned items.
    Missing selected UIDs are skipped as in native lookup; unknown templates
    fail closed. This API excludes hypothetical preview additions/removals.
    """
    templates, classes, slot_one = policy
    if type(selected_uids) is not tuple or type(equipment) is not tuple:
        raise ValueError('Explicit immutable equipment inputs required')
    if type(class_id) is not int or class_id not in classes:
        raise ValueError('Unresolved character class')
    if type(side) is not int or side not in (0, 1, 2):
        raise ValueError('Explicit character side required')
    if any(type(uid) is not int or not 0 < uid < 2**63 for uid in selected_uids):
        raise ValueError('Invalid selected UID')
    if len(set(selected_uids)) != len(selected_uids):
        raise ValueError('Repeated selected equipment instance')
    states = {}
    for row in equipment:
        if type(row) is not EquipmentState:
            raise ValueError('Explicit equipment state required')
        if type(row.uid) is not int or not 0 < row.uid < 2**63 or row.uid in states:
            raise ValueError('Invalid or repeated equipment instance')
        for value in (row.template, row.wrapper_type, row.wrapper_slot, row.item_0c, row.item_10, row.item_18):
            if type(value) is not int or not -2**31 <= value < 2**31:
                raise ValueError('Native signed field required')
        if type(row.category_4d) is not bool or (row.extension_7bd is not None and type(row.extension_7bd) is not bool):
            raise ValueError('Unresolved item validity metadata')
        states[row.uid] = row
    admitted = []
    family, branch, stage = classes[class_id]
    for uid in selected_uids:
        row = states.get(uid)
        if row is None or row.wrapper_type in (8, 14, 16):
            continue
        if row.template not in templates:
            raise ValueError('Non-avatar or unresolved original template')
        flags4, flags8, required_class = templates[row.template]
        # These pinned avatar records have no flag7 and no special-ID gate.
        if flags8 & 0xf8 in (8, 16) and not flags4 & 1:
            if not row.category_4d and row.item_18 < 0:
                continue
        if row.item_0c == 1 and row.item_10 <= 0:
            continue
        if row.category_4d and row.extension_7bd is False:
            continue
        if required_class:
            required_family, required_branch, required_stage = classes[required_class]
            if family != required_family or (required_branch and branch != required_branch) or stage < required_stage:
                continue
        if (flags4 & 1 or flags8 & 0xf8 == 24) and side != 2:
            slot = row.wrapper_slot
            signed_short = (slot + 32768) % 65536 - 32768
            item_side = 2 if slot in (1, 3, 5, 7, 9) else int(signed_short in slot_one)
            if item_side != 2 and item_side != side:
                continue
        admitted.append((uid, row.template))
    # Native 963540 sorts by signed item+8 (template ID), not by UID/slot.
    # Equal-template ordering is immaterial to selector/count projection.
    return tuple(sorted(admitted, key=lambda instance: instance[1]))
