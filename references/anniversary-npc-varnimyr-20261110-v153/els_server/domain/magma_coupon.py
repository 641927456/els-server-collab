"""Magma Breath's native reservation and single successful-clear consumption."""
import struct

from els_server.protocol.protocol_codec import Event, encode_event

DUNGEON = 35690
TEMPLATE = 721817
MULTIPLIER = 5
MISSION_THRESHOLD = 200
REQUEST = 0xc6c
REPLY = 0xc6d


def definition():
    from els_server.game_data import client_data

    item = client_data().item(TEMPLATE)
    stack = struct.unpack_from('<I', item['record'], 16)[0]
    if (item['metadata'], item['item_type'], stack) != (2, 7, 300):
        raise ValueError('Magma coupon native item identity')
    return dict(template=TEMPLATE, metadata=2, group=4, max_stack=stack)


def reserved(s):
    reservation = getattr(s, '_magma_coupon', None)
    origin = getattr(s, '_random_mission_origin', None)
    if reservation is not None and origin is not None and reservation[:3] == (origin, s.reward_run_id, s.account.uid):
        return reservation[3]
    return None


def _usable(item):
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked

    if item['template'] != TEMPLATE or item['group'] != 4 or item.get('sealed', False):
        return False
    try:
        require_current(item)
        require_unlocked(item)
    except ValueError:
        return False
    return True


def _reply(result):
    # C3C4D0 reads an i32 result and a vector of item bodies. Reservation has
    # no inventory delta. The ordinary clear writer publishes that separately.
    event = Event(0x201, kind=REPLY, payload=struct.pack('>iI', result, 0))
    encode_event(event)
    return [event]


def reserve(s, event):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.random_mission_flow import _origin
    from els_server.storage.inventory_state import load_items
    from els_server.storage.random_missions import _actor, saved
    from els_server.storage.read_scope import snapshot_connection

    if (event.payload != struct.pack('>ii', DUNGEON, TEMPLATE) or event.performers
            or event.uid != 2**64-1 or event.target_uid != 2**64-1 or event.payload_mode != 0
            or s.phase != 'dungeon_active' or s.dungeon_id != DUNGEON or s.dungeon_run is None
            or s.dungeon_run.identity != DUNGEON or not s.dungeon_substage_synced or s.gate_stage_loading
            or s.clear_notified or s.dungeon_failed or not current_lease(s)):
        return _reply(-1)
    try:
        context = _origin(s)
        if context is None:
            return _reply(-1)
        owner, account, run = s.account.uid, s.account.account_id, s.reward_run_id
        if reserved(s) is not None:
            return _reply(0)
        with snapshot_connection(s.account.store.path) as db:
            db.execute('BEGIN')
            _actor(db, owner, account)
            mission = saved(db, run, owner)
            if mission is not None and mission['percent'] >= MISSION_THRESHOLD:
                return _reply(-1)
            item = next((item for item in load_items(db, owner) if _usable(item)), None)
            if item is None:
                return _reply(60)
            result = _reply(0)
            if not current_lease(s) or _origin(s) != context:
                return _reply(-1)
            s._magma_coupon = (s._random_mission_origin, run, owner, item['uid'])
            return result
    except ValueError:
        return _reply(-1)


def settle(s, db, base, previous):
    """Return the boosted clear base and changed position in the original writer."""
    uid = reserved(s)
    if uid is None or base == 0:
        return base, None
    from els_server.storage.inventory_actions import _commit, _identity, _previous
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove

    operation = 'magma-coupon:' + s.reward_run_id
    owner, digest = _identity(s.account.uid, REQUEST, struct.pack('>iiQ', DUNGEON, TEMPLATE, uid), operation)
    positions = _previous(db, operation, digest)
    if previous:
        return (base * MULTIPLIER, positions[0]) if positions else (base, None)
    if positions is not None:
        raise ValueError('Magma coupon receipt without original clear')
    before = load_items(db, owner)
    item = next((item for item in before if item['uid'] == uid and _usable(item)), None)
    if item is None:
        return base, None
    position = item['group'], item['slot']
    if item['count'] == 1:
        remove(db, owner, item)
    else:
        db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?', (uid, owner))
    _commit(db, operation, digest, owner, REQUEST, [position], before, load_items(db, owner))
    return base * MULTIPLIER, position
