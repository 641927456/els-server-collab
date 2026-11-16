"""Native dungeon EXP coupon use; consume now, award on successful clear."""
import struct,sqlite3,json
from contextlib import closing

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


def _consume(db,owner,run,dungeon,template):
    """Original request writer; a repeated run/request returns current slots."""
    from els_server.storage.inventory_actions import _previous,_commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove
    from els_server.storage.equipment_receipt_state import current_changes
    if not db.in_transaction:raise ValueError('Coupon use requires original writer')
    operation,digest=_use_identity(owner,run,dungeon,template)
    old=_previous(db,operation,digest);before=load_items(db,owner)
    if old is not None:
        changes=current_changes(db,operation,owner,REQUEST,old,before)
        history=json.loads(db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0])
        uid=next(i['uid']for i in history if (i['group'],i['slot'])==old[0])
        return uid,changes
    item=next((i for i in before if _usable(i,template)),None)
    if item is None:return None,[]
    position=item['group'],item['slot']
    if item['count']==1:remove(db,owner,item)
    else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
    after=load_items(db,owner)
    _commit(db,operation,digest,owner,REQUEST,[position],before,after)
    current=next((i for i in after if (i['group'],i['slot'])==position),None)
    return item['uid'],[(position,current)]


def reserve(s, event):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.random_mission_flow import _origin
    from els_server.storage.random_missions import _actor, saved
    from els_server.storage.sqlite_timing import write_transaction

    from els_server.domain.experience_items import coupon
    if len(event.payload)!=8:return _reply(-1)
    dungeon,template=struct.unpack('>ii',event.payload)
    rule=coupon(dungeon,template)
    if (rule is None or event.performers
            or event.uid != 2**64-1 or event.target_uid != 2**64-1 or event.payload_mode != 0
            or s.phase != 'dungeon_active' or s.dungeon_id != dungeon or s.dungeon_run is None
            or s.dungeon_run.identity != dungeon or not s.dungeon_substage_synced or s.gate_stage_loading
            or s.clear_notified or s.dungeon_failed or not current_lease(s)):
        return _reply(-1)
    try:
        context = _origin(s)
        if context is None:
            return _reply(-1)
        owner, account, run = s.account.uid, s.account.account_id, s.reward_run_id
        if reserved(s) is not None and s._magma_coupon[4:]!=(dungeon,template):return _reply(-1)
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with write_transaction(db):
                _actor(db, owner, account)
                mission = saved(db, run, owner)
                if mission is not None and mission['percent'] >= rule['mission_threshold']:
                    return _reply(-1)
                uid,changes=_consume(db,owner,run,dungeon,template)
                if uid is None:
                    return _reply(60)
                result = _reply(0,changes)
                if not current_lease(s) or _origin(s) != context:
                    raise ValueError('Coupon use authority changed')
        s._magma_coupon = (s._random_mission_origin, run, owner, uid,dungeon,template)
        return result
    except ValueError:
        return _reply(-1)


def settle(s, db, base, previous):
    """Apply the committed use once; retain old clear receipt replay semantics."""
    uid = reserved(s)
    if uid is None or base == 0:
        return base, None
    dungeon,template=s._magma_coupon[4:]
    from els_server.domain.experience_items import coupon
    rule=coupon(dungeon,template)
    if rule is None or s.dungeon_id!=dungeon or s.dungeon_run.identity!=dungeon:
        raise ValueError('Experience coupon original dungeon changed')
    boosted=base*rule['percent']//100
    from els_server.storage.inventory_actions import _identity, _previous

    operation,digest=_use_identity(s.account.uid,s.reward_run_id,dungeon,template)
    used=_previous(db,operation,digest)
    if used is not None:return boosted,None
    if not previous:raise ValueError('Coupon clear has no committed use')

    # Existing 721817 clear receipts remain replayable without a second debit.
    operation = 'magma-coupon:' + s.reward_run_id
    owner, digest = _identity(s.account.uid, REQUEST, struct.pack('>iiQ', dungeon, template, uid), operation)
    positions = _previous(db, operation, digest)
    return (boosted, positions[0]) if positions else (base, None)
