"""Version1 undecorated own rooms and durable admission generations only.

The last ordinary town remains the login/return location. No unknown saved room
is migrated, no furniture/music/guestbook/visitor/renewal writer is provided.
"""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,time
from els_server.storage import housing_access
from els_server.storage.item_actor import require_active_character
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.housing_messages import entry_snapshot

WRITES_ENABLED=True
ROOM='character_housing_rooms_v1'
ADMISSIONS='housing_room_admissions'
LAYOUT='[[0,[0,0]]]'

def exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()is not None

def snapshot(db,uid,account_id):
    housing_access.owner(db,uid,account_id)
    if not exists(db,ROOM):return None
    row=db.execute('SELECT account_id,version,layout_json,floor_template,wall_template,created_at,generation FROM character_housing_rooms_v1 WHERE owner=?',(uid,)).fetchone()
    if row is None:return None
    if(row[:5]!=(account_id,1,LAYOUT,136037,136036)or any(type(v)is not int or not 0<v<2**63 for v in row[5:])):raise ValueError('Unknown housing room saved format')
    return dict(owner=uid,account_id=account_id,version=1,layout=[(0,(0,0))],floor_template=row[3],wall_template=row[4],created_at=row[5],generation=row[6])

def read(path,uid,account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:return snapshot(db,uid,account_id)

def dto(character,*,db=None,account=None):
    uid=character['uid'];name=character['name'];level=character['level'];base=character['unit_type']
    if type(uid)is not int or not 0<uid<2**63 or type(name)is not str or not 1<=level<=99 or type(base)is not int or not 0<=base<=15:raise ValueError('Housing native owner profile')
    # Explicit compatibility v1: opaque, currently unconsumed scalar fields
    # retain the same-client DTO ctor0/empty. Their related writers stay closed.
    #31 is actual occupancy,76 is the actual roster,8E is this roster's host.
    value={'000':0,'004':{'00':0,'08':uid,'10':'','30':0,'31':1,'32':'','52':0,'56':'','76':[uid],'8e':uid,'96':name},
        '0ba':'','0da':[(0,(0,0))],'0ea':0,'0ee':False,'0ef':0,'0f7':[],
        '107':{'00':0,'08':[],'20':0,'24':False,'25':False,'26':False,'27':[],'3f':0,'40':0},
        '14f':{'00':0,'02':'','22':0,'26':0,'2a':0,'32':name,'52':level,'53':base},
        '1a3':False,'1a4':[],'1c4':True,'1b4':[],'1c5':[]}

    if db is not None:
        from els_server.storage.housing_layouts import project
        project(db,uid,account,value)
    return value

def enter(path,uid,account_id,payload,operation,session_id,source_town,guard,*,now=None):
    from els_server.protocol.housing_messages import entry_request
    request=entry_request(payload)
    if request['kind']!=1 or request['target']!=0:raise ValueError('Only original own-room entry is admitted')
    if not callable(guard)or not isinstance(operation,str)or not 1<=len(operation)<=200:raise ValueError('Housing current actor operation')
    digest=hashlib.sha256(payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
        housing_access.owner(db,uid,account_id);require_active_character(db,uid)
        from els_server.storage.seal_quests import load_character,ensure
        character=load_character(db,uid,account_id);access=housing_access.snapshot(db,uid,account_id)
        if access is None or character['level']!=99:raise ValueError('Current first contract and level99 required')
        clock=int(time.time())if now is None else now
        if not housing_access.active(access,clock):raise ValueError('Housing access expired or clock before registration')
        old=db.execute('SELECT owner,account_id,session_id,request_hash,generation,source_town FROM housing_room_admissions WHERE operation_id=?',(operation,)).fetchone()if exists(db,ADMISSIONS)else None
        room=snapshot(db,uid,account_id)
        if room is not None and clock<room['created_at']:raise ValueError('Housing room clock before saved creation')
        if old is not None:
            if old[:4]!=(uid,account_id,session_id,digest)or old[5]!=source_town or room is None or old[4]>room['generation']:raise ValueError('Housing admission receipt mismatch')
            answer=[Event(0x201,kind=0x924,payload=entry_snapshot(dto(character,db=db,account=account_id)))];generation=old[4]
            for event in answer:encode_event(event)
            guard(db);return dict(events=answer,generation=generation,replayed=True,operation=operation,source_town=source_town)
        if not WRITES_ENABLED:raise ValueError('Housing room writer held')
        ensure(db)
        db.execute('CREATE TABLE IF NOT EXISTS character_housing_rooms_v1 (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1),layout_json TEXT NOT NULL,floor_template INTEGER NOT NULL CHECK(floor_template=136037),wall_template INTEGER NOT NULL CHECK(wall_template=136036),created_at INTEGER NOT NULL CHECK(created_at>0),generation INTEGER NOT NULL CHECK(generation>0))')
        db.execute('CREATE TABLE IF NOT EXISTS housing_room_admissions (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,session_id TEXT NOT NULL,request_hash TEXT NOT NULL,generation INTEGER NOT NULL CHECK(generation>0),source_town INTEGER NOT NULL,admitted_at INTEGER NOT NULL,quest_generation INTEGER,UNIQUE(owner,generation))')
        generation=1 if room is None else room['generation']+1
        if generation>=2**63:raise ValueError('Housing admission generation bound')
        if room is None:db.execute('INSERT INTO character_housing_rooms_v1 VALUES (?,?,?,?,?,?,?,?)',(uid,account_id,1,LAYOUT,136037,136036,clock,generation))
        else:db.execute('UPDATE character_housing_rooms_v1 SET generation=? WHERE owner=?',(generation,uid))
        active=db.execute('SELECT generation FROM character_quests WHERE owner=? AND quest=26770',(uid,)).fetchone()
        db.execute('INSERT INTO housing_room_admissions VALUES (?,?,?,?,?,?,?,?,?)',(operation,uid,account_id,session_id,digest,generation,source_town,clock,active[0]if active else None))
        from els_server.domain.housing_room_quest import admitted
        answer=[Event(0x201,kind=0x924,payload=entry_snapshot(dto(character,db=db,account=account_id)))]+admitted(db,uid,account_id,operation,generation)
        for event in answer:encode_event(event)
        guard(db)
        if not WRITES_ENABLED:raise ValueError('Housing room held before commit')
        snapshot(db,uid,account_id)
        return dict(events=answer,generation=generation,replayed=False,operation=operation,source_town=source_town)
