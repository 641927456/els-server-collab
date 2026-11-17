"""One atomic debit, native warp position, and existing durable receipt."""
from contextlib import closing
import hashlib,json,sqlite3,uuid
from els_server.domain import town_travel as rules
from els_server.domain.item_expiration import expired
from els_server.storage.inventory_state import load_items
from els_server.storage.seal_quests import load_character,completed_ids
from els_server.storage.reward_state import validate_balances,RewardConflict
from els_server.protocol import town_travel_messages as wire

def travel(path,uid,account_id,source,payload,operation,*,now,context=None,authorize=None,pending=None):
    if str(uuid.UUID(operation))!=operation:raise ValueError('Town warp receipt identity')
    destination,free,special,growth=wire.request(payload)
    if type(source) is not int or type(now) is not int or now<0:raise ValueError('Town warp source clock')
    if destination==1012:
        return _travel_village1012(path,uid,account_id,source,payload,operation,now=now,context=context,authorize=authorize,pending=pending)
    def guard():
        if authorize is not None and (not callable(authorize) or authorize() is not True):
            raise ValueError('Ordinary town warp current actor changed')
    proof=json.dumps(dict(owner=uid,account=account_id,source=source,payload=payload.hex()),sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(proof.encode()).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');guard();character=load_character(db,uid,account_id)
        previous=db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
        if previous:
            grant=json.loads(previous[1])
            if previous[0]!=digest or grant.get('kind')!='town_warp' or grant.get('owner')!=uid:raise RewardConflict('Conflicting town warp receipt')
            guard()
            return dict(response=bytes(previous[2]),balances=json.loads(previous[3]),grant=grant,replayed=True)
        saved=db.execute('SELECT town FROM location WHERE uid=?',(uid,)).fetchone()
        if saved!=(source,) or str(source) not in rules.catalog()['towns']:raise ValueError('Town warp current source mismatch')
        if source==destination:raise ValueError('Town warp same destination')
        records={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(uid,))}
        point=rules.require_destination(destination,character,completed_ids(db,uid),records)
        items=load_items(db,uid)
        passes=[i for i in items if i['template']==118149 and i['group']==4 and i['count']>0 and not expired(i,now=now)]
        # An owned, live118149 is a bag-presence waiver. No consumption/VIP timer.
        if free and not passes:raise ValueError('Town warp free entitlement expired or absent')
        fee=0 if passes else rules.price(source,destination,character['level'])
        before=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
        if before['ed']<fee:raise ValueError('Town warp insufficient ED')
        after=dict(before,ed=before['ed']-fee,revision=before['revision']+1)
        if after['revision']>=2**63:raise ValueError('Town warp revision overflow')
        grant=dict(kind='town_warp',owner=uid,source=source,destination=destination,fee=fee,pass_uid=passes[0]['uid'] if passes else None,flags=[free,special,growth])
        response=wire.acknowledgement(destination,after['ed']).payload
        if not isinstance(response,bytes) or len(response)!=32:raise ValueError('Town warp response encoding')
        from els_server.protocol.protocol_codec import encode_event
        encode_event(wire.acknowledgement(destination,after['ed']))
        guard()
        # Store the source-defined IsWarp coordinates with the charge. A
        # disconnect before225/227 therefore cold-loads the paid destination.
        db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',(after['ed'],after['revision'],uid))
        db.execute('UPDATE location SET town=?,board=0,progress=0,x=?,y=?,z=?,revision=revision+1 WHERE uid=?',(destination,*point['xyz'],uid))
        db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)',(operation,digest,json.dumps(grant,sort_keys=True),response,json.dumps(after,sort_keys=True)))
        return dict(response=response,balances=after,grant=grant,replayed=False)

def ordinary_committed_entry(path,uid,account_id,source,payload,operation,response,*,authorize):
    """Read-only proof for native225 flag1 after this session's paid58C."""
    from pathlib import Path
    if not callable(authorize) or authorize() is not True:raise ValueError('Town entry actor changed')
    destination,free,special,growth=wire.request(payload)
    if destination==1012 or source==destination:raise ValueError('Ordinary committed entry source')
    proof=json.dumps(dict(owner=uid,account=account_id,source=source,payload=payload.hex()),sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(proof.encode()).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN');load_character(db,uid,account_id)
        old=db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
        if old is None or old[0]!=digest:raise ValueError('Town entry missing exact committed receipt')
        grant=json.loads(old[1]);after=validate_balances(tuple(json.loads(old[3])[k]for k in('ed','experience','revision')))
        if(not isinstance(grant,dict)or set(grant)!={'kind','owner','source','destination','fee','pass_uid','flags'}
                or grant['kind']!='town_warp' or grant['owner']!=uid or grant['source']!=source
                or grant['destination']!=destination or grant['flags']!=[free,special,growth]
                or type(grant['fee'])is not int or grant['fee']<0):raise ValueError('Town entry receipt context')
        pass_uid=grant['pass_uid']
        if pass_uid is not None:
            if type(pass_uid)is not int or not 0<pass_uid<2**63 or grant['fee']!=0:raise ValueError('Town entry waiver receipt')
        elif free:raise ValueError('Town entry unproved free receipt')
        expected=wire.acknowledgement(destination,after['ed']).payload
        if not isinstance(response,bytes)or response!=bytes(old[2])or response!=expected:raise ValueError('Town entry committed response')
        location=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uid,)).fetchone()
        point=rules.catalog()['towns'][str(destination)]['xyz']
        if location!=(destination,0,0,*point):raise ValueError('Town entry current paid location')
        if authorize() is not True:raise ValueError('Town entry actor changed')
        return True

# Only the new1012 route uses this policy. Parent routes/receipts stay intact.
VILLAGE1012_POLICY = 'qualified-cobo-village1012-v1'
VILLAGE1012_WRITER_ENABLED = True


def _village1012_guard(db, uid, account_id, authorize):
    if not callable(authorize) or authorize() is not True:
        raise ValueError('Village1012 current session context')
    if type(uid) is not int or not 1001 <= uid < 2**63-1 or type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Village1012 actor identity')
    character = load_character(db, uid, account_id)
    # Match the current selector's finalized-character filter, not a new ban
    # on pending deletion. Read optional lifecycle state without creating it.
    from els_server.storage.character_lifecycle import states
    lifecycle = states(db, (uid,)).get(uid)
    if lifecycle and (lifecycle['account_id'] != account_id or lifecycle['finalized_at']):
        raise ValueError('Village1012 actor is unavailable')
    if type(character['level']) is not int or not 1 <= character['level'] <= 99:
        raise ValueError('Village1012 stored actor level')
    return character


def _village1012_balance(value):
    if not isinstance(value, dict) or set(value) != {'ed', 'experience', 'revision'}:
        raise ValueError('Village1012 balance shape')
    return validate_balances(tuple(value[k] for k in ('ed', 'experience', 'revision')))


def _village1012_location(value):
    from els_server.storage.local_state import validate_location
    keys = ('town', 'board', 'progress', 'x', 'y', 'z', 'revision')
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError('Village1012 location shape')
    if any(type(value[k]) is not int for k in ('town', 'board', 'progress', 'revision')) or not 0 <= value['revision'] < 2**63:
        raise ValueError('Village1012 location identity/revision')
    if any(type(value[k]) not in (int, float) for k in ('x', 'y', 'z')):
        raise ValueError('Village1012 coordinate type')
    validate_location(value['town'], value['board'], value['progress'], tuple(value[k] for k in ('x', 'y', 'z')))
    return value


def _village1012_snapshot(db, uid):
    location = db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?', (uid,)).fetchone()
    if location is None:
        raise ValueError('Village1012 missing saved location')
    balance = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (uid,)).fetchone())
    return dict(location=_village1012_location(dict(zip(('town','board','progress','x','y','z','revision'), location))), balance=balance)


def village1012_snapshot(path, uid, account_id, *, authorize):
    """Owned read only; also retained by the writer-closed recovery variant."""
    from pathlib import Path
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        _village1012_guard(db, uid, account_id, authorize)
        return _village1012_snapshot(db, uid)


def _village1012_context(uid, account_id, source, payload, operation, context):
    expected = {'account', 'owner', 'source', 'destination', 'session_id', 'sequence'}
    if not isinstance(context, dict) or set(context) != expected:
        raise ValueError('Village1012 operation context')
    if (context['account'] != account_id or context['owner'] != uid or context['source'] != source
            or context['destination'] != 1012 or type(context['sequence']) is not int
            or not 1 <= context['sequence'] < 2**32):
        raise ValueError('Village1012 operation actor/source')
    session_id = uuid.UUID(context['session_id'])
    if str(session_id) != context['session_id'] or session_id.version != 4:
        raise ValueError('Village1012 session epoch')
    expected_operation = str(uuid.uuid5(session_id, f'town-warp:{uid}:{context["sequence"]}'))
    if operation != expected_operation:
        raise ValueError('Village1012 operation epoch')
    destination, free, special, growth = wire.request(payload)
    if destination != 1012 or source == 1012 or type(source) is not int or str(source) not in rules.catalog()['towns']:
        raise ValueError('Village1012 operation destination/source')
    proof = json.dumps(dict(owner=uid, account=account_id, source=source, payload=payload.hex()), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(proof.encode()).hexdigest(), [free, special, growth]


def _village1012_binding(grant, digest):
    raw = json.dumps(grant, sort_keys=True, separators=(',', ':')).encode()
    return dict(policy=VILLAGE1012_POLICY, context=grant['context'], operation=grant['operation'],
                payload=grant['payload'], proof_sha256=digest, grant_sha256=hashlib.sha256(raw).hexdigest())


def _village1012_receipt(db, uid, account_id, source, payload, operation, context, digest, flags, previous, pending):
    from els_server.protocol.protocol_codec import Event, encode_event
    if previous is None:
        raise ValueError('Village1012 missing committed transition')
    grant = json.loads(previous[1])
    keys = {'kind','policy','owner','account','source','destination','operation','context','payload','fee','pass_uid','flags',
            'before_location','after_location','before_balance','after_balance'}
    if (not isinstance(grant, dict) or set(grant) != keys or previous[0] != digest
            or grant['kind'] != 'town_warp' or grant['policy'] != VILLAGE1012_POLICY
            or grant['owner'] != uid or grant['account'] != account_id or grant['source'] != source
            or grant['destination'] != 1012 or grant['operation'] != operation or grant['context'] != context
            or grant['payload'] != payload.hex() or grant['flags'] != flags):
        raise RewardConflict('Village1012 receipt identity/schema')
    before, after = _village1012_balance(grant['before_balance']), _village1012_balance(grant['after_balance'])
    left, right = _village1012_location(grant['before_location']), _village1012_location(grant['after_location'])
    fee, pass_uid = grant['fee'], grant['pass_uid']
    if (type(fee) is not int or not 0 <= fee <= before['ed']
            or (pass_uid is not None and (type(pass_uid) is not int or not 0 < pass_uid < 2**63))
            or (pass_uid is not None and fee != 0)
            or (pass_uid is None and (flags[0] or fee != rules.price(source, 1012, 99)))
            or after != dict(before, ed=before['ed']-fee, revision=before['revision']+1)
            or left['town'] != source or right != dict(left, town=1012, board=0, progress=0,
                x=rules.catalog()['towns']['1012']['xyz'][0], y=rules.catalog()['towns']['1012']['xyz'][1],
                z=rules.catalog()['towns']['1012']['xyz'][2], revision=left['revision']+1)
            or json.loads(previous[3]) != after):
        raise RewardConflict('Village1012 receipt before/after transition')
    response = wire.acknowledgement(1012, after['ed']).payload
    if bytes(previous[2]) != response:
        raise RewardConflict('Village1012 receipt response')
    encode_event(Event(0x201, kind=0x58d, payload=response))
    binding = _village1012_binding(grant, digest)
    if (not isinstance(pending, dict) or pending.get('binding') != binding or pending.get('operation') != operation
            or pending.get('destination') != 1012 or pending.get('payload') != payload
            or pending.get('sequence') != context['sequence'] or pending.get('response') != response
            or _village1012_snapshot(db, uid) != dict(location=right, balance=after)):
        raise RewardConflict('Village1012 current afterstate/pending changed')
    return dict(response=response, balances=after, grant=grant, binding=binding, replayed=True)


def village1012_committed(path, uid, account_id, source, payload, operation, context, pending, *, authorize):
    """Verify a committed same-session transition without mutating the receipt."""
    from pathlib import Path
    digest, flags = _village1012_context(uid, account_id, source, payload, operation, context)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        _village1012_guard(db, uid, account_id, authorize)
        old = db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?', (operation,)).fetchone()
        return _village1012_receipt(db, uid, account_id, source, payload, operation, context, digest, flags, old, pending)


def _travel_village1012(path, uid, account_id, source, payload, operation, *, now, context, authorize, pending):
    from els_server.protocol.protocol_codec import Event, encode_event
    if not VILLAGE1012_WRITER_ENABLED:
        raise ValueError('New Village1012 travel is closed; stored readers remain available')
    digest, flags = _village1012_context(uid, account_id, source, payload, operation, context)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        character = _village1012_guard(db, uid, account_id, authorize)
        previous = db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?', (operation,)).fetchone()
        if previous is not None:
            return _village1012_receipt(db, uid, account_id, source, payload, operation, context, digest, flags, previous, pending)
        if pending is not None:
            raise ValueError('Village1012 pending has no committed receipt')
        snapshot = _village1012_snapshot(db, uid)
        if snapshot['location']['town'] != source:
            raise ValueError('Village1012 current saved source')
        records = {r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?', (uid,))}
        point = rules.require_destination(1012, character, completed_ids(db, uid), records)
        items = load_items(db, uid)
        passes = [i for i in items if i['template']==118149 and i['group']==4 and i['count']>0 and not expired(i, now=now)]
        if flags[0] and not passes:
            raise ValueError('Village1012 free entitlement absent/expired')
        fee = 0 if passes else rules.price(source, 1012, character['level'])
        before, location = snapshot['balance'], snapshot['location']
        if before['ed'] < fee:
            raise ValueError('Village1012 insufficient ED')
        after = _village1012_balance(dict(before, ed=before['ed']-fee, revision=before['revision']+1))
        target = _village1012_location(dict(location, town=1012, board=0, progress=0,
                    x=point['xyz'][0], y=point['xyz'][1], z=point['xyz'][2], revision=location['revision']+1))
        grant = dict(kind='town_warp', policy=VILLAGE1012_POLICY, owner=uid, account=account_id,
                     source=source, destination=1012, operation=operation, context=context, payload=payload.hex(),
                     fee=fee, pass_uid=passes[0]['uid'] if passes else None, flags=flags,
                     before_location=location, after_location=target, before_balance=before, after_balance=after)
        event = wire.acknowledgement(1012, after['ed'])
        if not isinstance(event.payload, bytes) or len(event.payload) != 32:
            raise ValueError('Village1012 complete response width')
        encode_event(event)  # Full existing Event serializer, before any write.
        db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?', (after['ed'], after['revision'], uid))
        db.execute('UPDATE location SET town=?,board=0,progress=0,x=?,y=?,z=?,revision=? WHERE uid=?',
                   (1012, target['x'], target['y'], target['z'], target['revision'], uid))
        db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)', (operation,digest,json.dumps(grant,sort_keys=True,separators=(',',':')),event.payload,json.dumps(after,sort_keys=True)))
        return dict(response=event.payload, balances=after, grant=grant, binding=_village1012_binding(grant,digest), replayed=False)
