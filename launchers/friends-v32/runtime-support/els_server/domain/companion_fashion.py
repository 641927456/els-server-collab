"""Resolve already-supported fashion slots using the pinned native minor enum.

NOW_EQIP_SLOT_ID explicitly separates Lu and Ciel. This does not register new
item templates or infer companion slots from an arithmetic offset.
"""
import functools
import json
import struct
from itertools import islice
from els_server.game_data import client_data


@functools.lru_cache(maxsize=1)
def _slot_maps(raw):
    # ClientData supplies verified immutable catalog text. Key the parsed maps
    # by that actual text, so a different static Enum cannot reuse old slots.
    slots = json.loads(raw)['NOW_EQIP_SLOT_ID']
    names = {value: name for name, value in slots.items()
             if name.startswith('NESI_') and not name.startswith('NESI_MINORUNIT_')}
    return slots, names


def resolve_slots(existing):
    data = client_data()
    records = _batch_records(data, existing)
    try:
        return _resolve_slots(existing, lambda template: next(records))
    finally:
        records.close()


def _batch_records(data, existing):
    # Only static catalog rows, at most256 at a time. Decode the same item
    # fields in original iteration order so malformed data fails as before.
    templates = iter(existing)
    with data.connect() as db:
        while chunk := list(islice(templates, 256)):
            ids = [t for t in chunk if type(t) is int and -2**63 <= t < 2**63]
            rows = {t: (record, stats, bonus) for t, record, stats, bonus in db.execute(
                'SELECT id,record,stats,stat_bonus FROM items WHERE id IN (' +
                ','.join('?' for _ in ids) + ')', ids)} if ids else {}
            for template in chunk:
                if type(template) is not int or not -2**63 <= template < 2**63:
                    yield data.item(template)['record']
                    continue
                if template not in rows:
                    raise ValueError(f'Unknown client item: {template}')
                record, stats, bonus = rows[template]
                struct.unpack('<7f', stats)
                tuple(bonus)
                yield record


def resolve_slots_from_records(existing, records):
    # Internal startup caller supplies the transient, SHA-verified manufacture
    # records. This does not cache item state or change the ordinary API.
    return _resolve_slots(existing, records.__getitem__)


def _resolve_slots(existing, record_for):
    data = client_data()
    slots, names = _slot_maps(data._resource('Enum.lua'))
    result = dict(existing)
    for template, slot in existing.items():
        record = record_for(template)
        if not record[8] & 4:
            continue
        if record[210] != 10:
            raise ValueError('Companion fashion belongs to Lu/Ciel')
        name = names.get(slot)
        minor = 'NESI_MINORUNIT_' + name[5:] if name else ''
        if minor not in slots:
            raise ValueError('Unverified companion fashion slot')
        result[template] = slots[minor]
    return result
