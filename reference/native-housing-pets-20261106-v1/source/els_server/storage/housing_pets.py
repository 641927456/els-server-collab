"""Owned pet placement, completed-cycle affinity and deadline release in one writer."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,struct,time
from els_server.domain.housing_pet_rules import MATS,mat
from els_server.protocol import housing_pet_messages as wire,pet_progression_messages as progress
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import housing_access,housing_rooms

TABLE='character_housing_pets_v1'
RECEIPTS='housing_pet_receipts'
WRITES_ENABLED=True


def exists(db):
    return housing_rooms.exists(db,TABLE)


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS character_housing_pets_v1 (
      owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
      account_id INTEGER NOT NULL,slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 4),
      pet INTEGER NOT NULL UNIQUE REFERENCES companions(uid) ON DELETE CASCADE,
      mat_uid INTEGER NOT NULL CHECK(mat_uid>0),mat_template INTEGER NOT NULL,
      started_at INTEGER NOT NULL CHECK(started_at>0),period INTEGER NOT NULL CHECK(period IN(28800,86400)),
      deadline INTEGER NOT NULL CHECK(deadline>started_at),PRIMARY KEY(owner,slot))''')
    db.execute('''CREATE TABLE IF NOT EXISTS housing_pet_receipts (
      operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
      account_id INTEGER NOT NULL,digest TEXT NOT NULL)''')


def saved(db,owner):
    if not exists(db):return []
    rows=db.execute('SELECT account_id,slot,pet,mat_uid,mat_template,started_at,period,deadline FROM '+TABLE+' WHERE owner=? ORDER BY slot',(owner,)).fetchall()
    for account,slot,pet,uid,template,start,period,end in rows:
        if(template not in MATS or MATS[template][1]!=period or not 1<=slot<=MATS[template][0]
           or any(type(v)is not int or v<=0 for v in(account,pet,uid,start,end))or end<=start):
            raise ValueError('Unknown saved housing pet placement')
    if len({(r[3],r[4])for r in rows})>1:
        raise ValueError('Saved housing pets use different mats')
    return rows


def projection(db,owner,account):
    housing_access.owner(db,owner,account)
    rows=saved(db,owner)
    if any(r[0]!=account for r in rows):raise ValueError('Housing pet saved account changed')
    if not rows:return []
    from els_server.storage.companion_state import rows as pets
    owned={p['uid']:p for p in pets(db,owner,'pet')}
    if any(r[2]not in owned for r in rows):raise ValueError('Housing pet ownership changed')
    # The additional native byte remains its original DTO constructor zero.
    # This finite layout has only the original first floor; no unverified
    # expansion/floor semantics are inferred from that auxiliary byte.
    return [(r[1],0,r[5],owned[r[2]])for r in rows]


def initialization(path,owner,account):
    from els_server.storage.read_scope import snapshot_connection
    with snapshot_connection(path)as db:
        return wire.placement_restore(projection(db,owner,account))


def require_available(db,owner,pet):
    if exists(db)and db.execute('SELECT 1 FROM '+TABLE+' WHERE owner=? AND pet=?',(owner,pet)).fetchone():
        raise ValueError('Pet is placed in housing; retrieve it first')


def validate_layout(db,owner,layout):
    rows=saved(db,owner)
    if rows:
        target=mat(layout)
        if target is None or any((r[3],r[4])!=(target['uid'],target['template'])for r in rows):
            raise ValueError('Retrieve housing pets before removing their mat')


def _release(db,owner,rows,clock):
    if not rows:return []
    if not db.in_transaction:raise ValueError('Housing pet release requires writer')
    from els_server.storage.companion_state import rows as pets
    from els_server.storage import pet_progression
    from els_server.domain.pet_progression import threshold
    owned={p['uid']:p for p in pets(db,owner,'pet')};answer=[]
    for account,slot,uid,mat_uid,template,start,period,end in rows:
        housing_access.owner(db,owner,account)
        if uid not in owned or clock<start:raise ValueError('Housing pet release identity/clock')
        pet=owned[uid];cycles=(min(clock,end)-start)//period;maximum=threshold(pet)
        # One percentage point per completed original period. Integer DTOs
        # use the first representable point at or above that percentage.
        pet['growth']=min(maximum,pet['growth']+(maximum*cycles+99)//100)
        pet_progression.save(db,owner,pet)
        if db.execute('DELETE FROM '+TABLE+' WHERE owner=? AND slot=? AND pet=?',(owner,slot,uid)).rowcount!=1:
            raise ValueError('Housing pet release changed')
        answer.extend((progress.progress(owner,pet),progress.refresh(owner,pet)))
    return answer


def expire(db,owner,clock):
    return _release(db,owner,[r for r in saved(db,owner)if clock>=r[7]],clock)


def renew(db,owner,deadline,clock):
    answer=expire(db,owner,clock)
    if exists(db):db.execute('UPDATE '+TABLE+' SET deadline=? WHERE owner=?',(deadline,owner))
    return answer


def periodic(path,owner,*,now=None,timeout=10):
    from els_server.storage.read_scope import snapshot_connection
    clock=int(time.time())if now is None else now
    with snapshot_connection(path)as probe:
        if not exists(probe)or not probe.execute('SELECT 1 FROM '+TABLE+' WHERE owner=? AND deadline<=? LIMIT 1',(owner,clock)).fetchone():return []
    with closing(sqlite3.connect(path,timeout=timeout))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        answer=expire(db,owner,clock)
        if not answer:return []
        account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
        if account is None:raise ValueError('Housing pet expiry owner missing')
        answer.append(wire.placement_restore(projection(db,owner,account[0])))
        for event in answer:encode_event(event)
        return answer


def perform(path,owner,account,kind,payload,operation,generation,admission,guard,*,now=None):
    if kind not in(0xa38,0xa3a):raise ValueError('Unknown housing pet operation')
    slot,uid=wire.placement_request(payload)
    if(not 1<=slot<=4 or not 0<uid<2**63 or type(operation)is not str or not 1<=len(operation)<=200
       or not callable(guard)):raise ValueError('Housing pet writer input')
    digest=hashlib.sha256(struct.pack('>I',kind)+payload).hexdigest()
    with closing(sqlite3.connect(Path(path),timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_actor import require_active_character
        guard(db);require_active_character(db,owner);housing_access.owner(db,owner,account)
        clock=int(time.time())if now is None else now
        if type(clock)is not int or clock<=0:raise ValueError('Housing pet server clock')
        room=housing_rooms.snapshot(db,owner,account)
        admitted=db.execute('SELECT owner,account_id,generation FROM housing_room_admissions WHERE operation_id=?',(admission,)).fetchone()
        if room is None or room['generation']!=generation or admitted!=(owner,account,generation):
            raise ValueError('Housing pet durable admission changed')
        old=db.execute('SELECT owner,account_id,digest FROM '+RECEIPTS+' WHERE operation=?',(operation,)).fetchone()if housing_rooms.exists(db,RECEIPTS)else None
        if old is not None:
            if old!=(owner,account,digest):raise ValueError('Housing pet receipt collision')
            answer=[wire.placement_ack(0,projection(db,owner,account),kind=kind+1)]
        else:
            if not WRITES_ENABLED:raise ValueError('Housing pet writer held')
            rows=saved(db,owner);expired=[r for r in rows if clock>=r[7]]
            answer=_release(db,owner,expired,clock)
            rows=[r for r in rows if r not in expired]
            if kind==0xa38:
                access=housing_access.snapshot(db,owner,account)
                if not housing_access.active(access,clock):raise ValueError('Housing pet current contract required')
                from els_server.storage.housing_layouts import snapshot as layout_snapshot
                layout=layout_snapshot(db,owner,account,now=clock)
                target=None if layout is None else mat(layout['layout'])
                if target is None or slot>target['capacity']:raise ValueError('Housing pet mat/slot required')
                if any(r[1]==slot or r[2]==uid for r in rows):raise ValueError('Housing pet slot or pet already placed')
                from els_server.storage.pet_support import owned_pet
                pet=owned_pet(db,owner,uid,now=clock)
                active=db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone()
                if(active and active[0]==uid)or pet.get('expires_at',0)or 20000<=pet['unit']<=25000:
                    raise ValueError('Housing requires unsummoned permanent ordinary pet')
                ensure(db)
                db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?,?,?,?,?,?,?)',(owner,account,slot,uid,target['uid'],target['template'],clock,target['period'],access['expires_at']))
            else:
                current=next((r for r in rows if(r[1],r[2])==(slot,uid)),None)
                if current is None and not any((r[1],r[2])==(slot,uid)for r in expired):
                    raise ValueError('Housing selected placed pet changed')
                if current is not None:answer+=_release(db,owner,[current],clock)
                ensure(db)
            db.execute('INSERT INTO '+RECEIPTS+' VALUES (?,?,?,?)',(operation,owner,account,digest))
            answer.append(wire.placement_ack(0,projection(db,owner,account),kind=kind+1))
        for event in answer:encode_event(event)
        guard(db)
        if not WRITES_ENABLED:raise ValueError('Housing pet writer changed before commit')
        return answer
