"""Resolve already-supported fashion slots using the pinned native minor enum.

NOW_EQIP_SLOT_ID explicitly separates Lu and Ciel. This does not register new
item templates or infer companion slots from an arithmetic offset.
"""
from els_server.game_data import client_data


def resolve_slots(existing):
    data = client_data()
    slots = data.resource('Enum.lua')['NOW_EQIP_SLOT_ID']
    names = {value: name for name, value in slots.items()
             if name.startswith('NESI_') and not name.startswith('NESI_MINORUNIT_')}
    result = dict(existing)
    for template, slot in existing.items():
        item = data.item(template)
        if not item['record'][8] & 4:
            continue
        if item['record'][210] != 10:
            raise ValueError('Companion fashion belongs to Lu/Ciel')
        name = names.get(slot)
        minor = 'NESI_MINORUNIT_' + name[5:] if name else ''
        if minor not in slots:
            raise ValueError('Unverified companion fashion slot')
        result[template] = slots[minor]
    return result
