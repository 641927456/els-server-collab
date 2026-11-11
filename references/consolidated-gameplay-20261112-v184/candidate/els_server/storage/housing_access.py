"""Character housing access, including the original seven-day and permanent contracts."""
import json
import sqlite3,time
from pathlib import Path
from contextlib import closing
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.domain.housing_contracts import RENEWAL_SECONDS,RENEWALS
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.housing_access_messages import lifetime,notice,PERMANENT
from els_server.protocol.protocol_codec import encode_event

WRITES_ENABLED=True

class HousingAccessError(ValueError):
    def __init__(self,result,message):
        super().__init__(message)
        self.result=result

TABLE='character_housing_access'
TEMPLATE=136034
SECONDS=7*24*60*60
PERMANENT_TEMPLATE=713275
TEMPLATES=frozenset((TEMPLATE,PERMANENT_TEMPLATE))|RENEWALS
PERMANENT_TABLE='character_housing_permanent'
PERMANENT_SQL='CREATE TABLE character_housing_permanent (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template=713275),source_uid INTEGER NOT NULL CHECK(source_uid>0),registered_at INTEGER NOT NULL CHECK(registered_at>0))'
EXTENSION_TABLE='character_housing_extensions'
EXTENSION_SQL=(
    'CREATE TABLE character_housing_extensions ('
    'owner INTEGER PRIMARY KEY REFERENCES characters(uid),'
    'account_id INTEGER NOT NULL CHECK(account_id>0),'
    'template INTEGER NOT NULL CHECK(template IN (136035,136088)),'
    'source_uid INTEGER NOT NULL CHECK(source_uid>0),'
    'registered_at INTEGER NOT NULL CHECK(registered_at>0),'
    f'expires_at INTEGER NOT NULL CHECK(expires_at>registered_at AND expires_at<{PERMANENT}))'
)

def permanent_snapshot(db,uid,account_id):
    schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(PERMANENT_TABLE,)).fetchone()
    if schema is None:return None
    if schema!=(PERMANENT_SQL,):raise ValueError('Unknown permanent housing schema')
    row=db.execute('SELECT account_id,template,source_uid,registered_at FROM character_housing_permanent WHERE owner=?',(uid,)).fetchone()
    if row is None:return None
    if(row[:2]!=(account_id,PERMANENT_TEMPLATE)or any(type(v)is not int or not 0<v<2**63 for v in row[2:])):raise ValueError('Permanent housing access integrity')
    return dict(template=row[1],source_uid=row[2],registered_at=row[3],expires_at=PERMANENT,permanent=True)


def exists(db):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()is not None

def owner(db,uid,account_id):
    if type(account_id)is not int or not 0<account_id<2**63:raise ValueError('Housing account identity')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Housing owner mismatch')

def timed_snapshot(db,uid,account_id):
    owner(db,uid,account_id)
    if not exists(db):return None
    row=db.execute('SELECT account_id,template,source_uid,registered_at,expires_at FROM character_housing_access WHERE owner=?',(uid,)).fetchone()
    if row is None:return None
    if(row[0]!=account_id or row[1]!=TEMPLATE or any(type(v)is not int or not 0<v<2**63 for v in row[2:])or row[4]-row[3]!=SECONDS):raise ValueError('Housing access integrity')
    lifetime(row[4]);return dict(template=row[1],source_uid=row[2],registered_at=row[3],expires_at=row[4])

def extension_snapshot(db,uid,account_id):
    schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(EXTENSION_TABLE,)).fetchone()
    if schema is None:return None
    if schema!=(EXTENSION_SQL,):raise ValueError('Unknown housing extension schema')
    row=db.execute('SELECT account_id,template,source_uid,registered_at,expires_at FROM character_housing_extensions WHERE owner=?',(uid,)).fetchone()
    if row is None:return None
    account,template,source_uid,registered_at,expires_at=row
    if (account!=account_id or template not in RENEWALS
            or any(type(value)is not int for value in row)
            or not 0<source_uid<2**63 or not 0<registered_at<expires_at<PERMANENT
            or expires_at-registered_at<RENEWAL_SECONDS[template]):
        raise ValueError('Housing extension integrity')
    return dict(template=template,source_uid=source_uid,registered_at=registered_at,expires_at=expires_at)

def snapshot(db,uid,account_id):
    timed=timed_snapshot(db,uid,account_id)
    extension=extension_snapshot(db,uid,account_id)
    return permanent_snapshot(db,uid,account_id)or extension or timed

def active(state,clock):
    return(type(clock)is int and state is not None and state['registered_at']<=clock
           and(state.get('permanent')is True or clock<state['expires_at']))

def read(path,uid,account_id):
    with snapshot_connection(path)as db:return snapshot(db,uid,account_id)

def consumed_template(db,operation,uid,source_uid,positions):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(uid,0x219) or len(positions)!=1:
        raise ValueError('Housing receipt identity')
    try:
        before,after=(json.loads(raw) for raw in row[2:])
        if not isinstance(before,list) or not isinstance(after,list):
            raise ValueError('Housing receipt item arrays')
        sources=[item for item in before if item['uid']==source_uid]
        if len(sources)!=1 or any(item['uid']==source_uid or (item['group'],item['slot'])==positions[0] for item in after):
            raise ValueError('Housing receipt contract was not consumed')
        source=sources[0]
        if (source['template'] not in TEMPLATES or (source['metadata'],source['count'],source['group'])!=(0,1,4)
                or (source['group'],source['slot'])!=positions[0]):
            raise ValueError('Housing receipt contract identity')
    except (TypeError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Housing receipt history format') from exc
    return source['template']

def use(path,uid,account_id,payload,operation,guard,*,now=None):
    source_uid=use_request(payload)
    uid,digest=_identity(uid,0x219,b'Housing136034:'+payload,operation)
    if not callable(guard):raise ValueError('Housing current actor guard required')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,uid)
        before=load_items(db,uid);old=_previous(db,operation,digest)
        state=snapshot(db,uid,account_id)
        item=next((i for i in before if i['uid']==source_uid),None)
        if old is None and(item is None or item['template']not in TEMPLATES):return None
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None or type(balance[0])is not int or not 0<=balance[0]<2**63:raise ValueError('Housing ED read integrity')
        if old is not None:
            if state is None:raise ValueError('Housing receipt access missing')
            template=consumed_template(db,operation,uid,source_uid,old)
            position=old[0]
            current=next((entry for entry in before if (entry['group'],entry['slot'])==position),None)
            answer=[use_ack([(position,current)],template,balance[0]),notice(state['expires_at'])]
            for event in answer:encode_event(event)
            guard(db);return answer
        if not WRITES_ENABLED:raise ValueError('Housing access writer held')
        template=item['template']
        if state is not None and(template==TEMPLATE or state.get('permanent')is True):
            raise HousingAccessError(2440 if state.get('permanent')is True else 2412,'Housing already owned')
        if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise HousingAccessError(2420,'Housing requires level99')
        if(item['metadata'],item['count'],item['group'])!=(0,1,4):raise ValueError('Housing original singleton contract')
        # Sample only after the real SQL writer and actor authorization.
        if now is None:now=int(time.time())
        if type(now)is not int or not 0<now<PERMANENT:raise ValueError('Housing registration clock')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item,now=now)
        if item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Housing sealed contract')
        if template==PERMANENT_TEMPLATE:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(PERMANENT_TABLE,)).fetchone()is None:db.execute(PERMANENT_SQL)
            db.execute('INSERT INTO character_housing_permanent VALUES (?,?,?,?,?)',(uid,account_id,template,source_uid,now))
            expiry=PERMANENT
        elif template in RENEWALS:
            if state is not None and now<state['registered_at']:raise ValueError('Housing renewal before current registration')
            start=state['expires_at'] if active(state,now) else now
            expiry=lifetime(start+RENEWAL_SECONDS[template])
            if expiry>=PERMANENT:raise ValueError('Housing timed expiry reaches permanent date')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(EXTENSION_TABLE,)).fetchone()is None:db.execute(EXTENSION_SQL)
            db.execute('''INSERT INTO character_housing_extensions VALUES (?,?,?,?,?,?)
                ON CONFLICT(owner) DO UPDATE SET template=excluded.template,source_uid=excluded.source_uid,
                    registered_at=excluded.registered_at,expires_at=excluded.expires_at''',
                (uid,account_id,template,source_uid,now,expiry))
        else:
            expiry=lifetime(now+SECONDS)
            if expiry>=PERMANENT:raise ValueError('Housing timed expiry reaches permanent date')
            db.execute('CREATE TABLE IF NOT EXISTS character_housing_access (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template=136034),source_uid INTEGER NOT NULL CHECK(source_uid>0),registered_at INTEGER NOT NULL CHECK(registered_at>0),expires_at INTEGER NOT NULL CHECK(expires_at>registered_at))')
            db.execute('INSERT INTO character_housing_access VALUES (?,?,?,?,?,?)',(uid,account_id,TEMPLATE,source_uid,now,expiry))
        from els_server.storage.housing_pets import renew
        pet_events=renew(db,uid,expiry,now)
        if pet_events:
            from els_server.protocol.housing_pet_messages import placement_restore
            from els_server.storage.housing_pets import projection
            pet_events.append(placement_restore(projection(db,uid,account_id)))
        remove(db,uid,item);after=load_items(db,uid);positions=[(item['group'],item['slot'])]
        answer=[use_ack([(positions[0],None)],template,balance[0]),notice(expiry)]+pet_events
        for event in answer:encode_event(event)
        guard(db)
        if not WRITES_ENABLED:raise ValueError('Housing access held before commit')
        snapshot(db,uid,account_id)
        _commit(db,operation,digest,uid,0x219,positions,before,after)
        return answer

from els_server.storage.read_scope import snapshot_connection
