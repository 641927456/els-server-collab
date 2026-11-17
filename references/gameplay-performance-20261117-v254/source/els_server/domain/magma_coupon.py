"""Native EXP coupon reservation; debit with the successful clear reward."""
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


def _usable(item, template):
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked

    if item['template'] != template or item['group'] != 4 or item.get('sealed', False):
        return False
    try:
        require_current(item)
        require_unlocked(item)
    except ValueError:
        return False
    return True


def _reply(result,changes=()):
    # C3C4D0 reads i32 result then the ordinary DD46E0 inventory vector.
    from els_server.domain.fashion_state import move_ack
    event = Event(0x201, kind=REPLY, payload=struct.pack('>i', result)+move_ack(changes)[:-4])
    encode_event(event)
    return [event]


def _use_identity(owner,run,dungeon,template):
    from els_server.storage.inventory_actions import _identity
    operation='exp-coupon-use:'+run+':'+str(owner)
    _,digest=_identity(owner,REQUEST,struct.pack('>ii',dungeon,template),operation)
    return operation,digest


def reserve(s, event):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.random_mission_flow import _origin
    from els_server.storage.random_missions import _actor, saved
    from els_server.storage.read_scope import snapshot_connection
    from els_server.storage.inventory_state import load_items

    from els_server.domain.experience_items import coupon
    if len(event.payload)!=8:return _reply(3013)
    dungeon,template=struct.unpack('>ii',event.payload)
    rule=coupon(dungeon,template)
    if (rule is None or event.performers
            or event.uid != 2**64-1 or event.target_uid != 2**64-1 or event.payload_mode != 0
            or s.phase != 'dungeon_active' or s.dungeon_id != dungeon or s.dungeon_run is None
            or s.dungeon_run.identity != dungeon or not s.dungeon_substage_synced or s.gate_stage_loading
            or s.clear_notified or s.dungeon_failed or not current_lease(s)):
        return _reply(3013)
    try:
        context = _origin(s)
        if context is None:
            return _reply(3013)
        owner, account, run = s.account.uid, s.account.account_id, s.reward_run_id
        if reserved(s) is not None:
            return _reply(0 if s._magma_coupon[4:] == (dungeon,template) else 3013)
        with snapshot_connection(s.account.store.path) as db:
            db.execute('BEGIN')
            _actor(db, owner, account)
            mission = saved(db, run, owner)
            if mission is not None and mission['percent'] >= rule['mission_threshold']:
                return _reply(3016)
            item=next((i for i in load_items(db,owner) if _usable(i,template)),None)
            if item is None:
                return _reply(3014)
            result = _reply(0)
            if not current_lease(s) or _origin(s) != context:
                raise ValueError('Coupon reservation authority changed')
        s._magma_coupon = (s._random_mission_origin, run, owner, item['uid'],dungeon,template)
        return result
    except ValueError:
        return _reply(3013)


def settle(s, db, base, previous):
    """Debit the reserved instance inside the original clear/reward transaction."""
    uid = reserved(s)
    if uid is None or base == 0:
        return base, None
    dungeon,template=s._magma_coupon[4:]
    from els_server.domain.experience_items import coupon
    rule=coupon(dungeon,template)
    if rule is None or s.dungeon_id!=dungeon or s.dungeon_run.identity!=dungeon:
        raise ValueError('Experience coupon original dungeon changed')
    if not db.in_transaction:raise ValueError('Coupon clear requires original writer')
    boosted=base*rule['percent']//100
    from els_server.storage.inventory_actions import _identity, _previous, _commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove

    # V236-V248 use receipts have already debited the item. Keep them readable
    # without charging again; new reservations never write this receipt kind.
    operation,digest=_use_identity(s.account.uid,s.reward_run_id,dungeon,template)
    if _previous(db,operation,digest) is not None:return boosted,None

    operation = 'magma-coupon:' + s.reward_run_id
    owner, digest = _identity(s.account.uid, REQUEST, struct.pack('>iiQ', dungeon, template, uid), operation)
    positions = _previous(db, operation, digest)
    if previous:
        return (boosted, positions[0]) if positions else (base, None)
    if positions is not None:
        raise ValueError('Coupon debit receipt without original clear')
    before=load_items(db,owner)
    item=next((i for i in before if i['uid']==uid and _usable(i,template)),None)
    if item is None:return base,None
    position=item['group'],item['slot']
    if item['count']==1:remove(db,owner,item)
    else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(uid,owner))
    _commit(db,operation,digest,owner,REQUEST,[position],before,load_items(db,owner))
    return boosted,position
