"""Native item-specific quest records consumed by DA3620/DD7EA0.

Unlike character quests, these records bind progress/history to an item UID.
The original RaidQuestSystem derives its localized previews from both lists.
"""
import struct
from els_server.protocol.protocol_codec import Event


def active_record(row):
    objectives = row['objectives']
    # The native UI keys this record by its middle Q (item UID). The two
    # other Q fields are retained metadata with no verified UI use.
    return struct.pack('>iQQQI', row['id'], 0, row['item_uid'],
                       0, len(objectives)) + b''.join(
        struct.pack('>iHB', sub, count, int(count >= limit))
        for sub, count, limit in _objectives(row))


def _objectives(row):
    from els_server.domain.weapon_growth import quest
    definition = quest(row['id'] - 1)
    for sub, count in sorted(row['objectives'].items()):
        yield sub, count, definition['target']


def completed_record(row):
    return struct.pack('>iQiQQ', row['id'], row['item_uid'], 1, 0, 0)


def initialization_tail(state):
    active = state.get('item_active', ())
    completed = state.get('item_completed', ())
    return struct.pack('>I', len(active)) + b''.join(active_record(row) for row in active) + \
        struct.pack('>I', len(completed)) + b''.join(completed_record(row) for row in completed)


def progress(rows):
    return Event(0x201, kind=0x96b, payload=struct.pack('>I', len(rows)) +
                 b''.join(active_record(row) for row in rows))


def request(payload):
    if not isinstance(payload, bytes) or len(payload) != 13:
        raise ValueError('Weapon growth request size')
    quest_id, item_uid, ui_flag = struct.unpack('>iQB', payload)
    if not 1 <= quest_id <= 5 or not 0 < item_uid < 2**63 or ui_flag not in (0, 1):
        raise ValueError('Weapon growth request fields')
    return quest_id, item_uid, ui_flag


def acknowledge(quest_id, item_uid, unit, result=0):
    # 23BE500 reads the same C5F7F0 inner state as quest F5, with no F5 flags.
    head = struct.pack('>iiQiQQ', result, quest_id, item_uid, 1, 0, 0)
    return Event(0x201, kind=0x96d, payload=head + unit)
