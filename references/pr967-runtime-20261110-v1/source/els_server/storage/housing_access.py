"""Native seven-day first access and current713275 permanent contract."""
import sqlite3,time
from pathlib import Path
from contextlib import closing
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.housing_access_messages import lifetime,notice,PERMANENT
from els_server.protocol.protocol_codec import encode_event

WRITES_ENABLED=True
TABLE='character_housing_access'
TEMPLATE=136034
SECONDS=7*24*60*60
PERMANENT_TEMPLATE=713275
TEMPLATES=(TEMPLATE,PERMANENT_TEMPLATE)
PERMANENT_TABLE='character_housing_permanent'
PERMANENT_SQL='CREATE TABLE character_housing_permanent (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template=713275),source_uid INTEGER NOT NULL CHECK(source_uid>0),registered_at INTEGER NOT NULL CHECK(registered_at>0))'

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

def snapshot(db,uid,account_id):
    owner(db,uid,account_id)
    timed=timed_snapshot(db,uid,account_id)
    return permanent_snapshot(db,uid,account_id)or timed

def active(state,clock):
    return(type(clock)is int and state is not None and state['registered_at']<=clock
           and(state.get('permanent')is True or clock<state['expires_at']))

def read(path,uid,account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:return snapshot(db,uid,account_id)

def use(path,uid,account_id,payload,operation,guard,*,now=None):
    source_uid=use_request(payload)
    uid,digest=_identity(uid,0x219,b'Housing136034:'+payload,operation)
    if not callable(guard):raise ValueError('Housing current actor guard required')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);owner(db,uid,account_id);require_active_character(db,uid)
        before=load_items(db,uid);old=_previous(db,operation,digest)
        state=snapshot(db,uid,account_id)
        item=next((i for i in before if i['uid']==source_uid),None)
        if old is None and(item is None or item['template']not in TEMPLATES):return None
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None or type(balance[0])is not int or not 0<=balance[0]<2**63:raise ValueError('Housing ED read integrity')
        if old is not None:
            proof=next((v for v in(timed_snapshot(db,uid,account_id),permanent_snapshot(db,uid,account_id))if v is not None and v['source_uid']==source_uid),None)
            if state is None or proof is None:raise ValueError('Housing receipt access missing')
            changes=current_changes(db,operation,uid,0x219,old,before)
            answer=[use_ack(changes,proof['template'],balance[0]),notice(state['expires_at'])]
            for event in answer:encode_event(event)
            guard(db);return answer
        if not WRITES_ENABLED:raise ValueError('Housing access writer held')
        template=item['template']
        if state is not None and(template==TEMPLATE or state.get('permanent')is True):raise ValueError('Housing already owned or timed renewal outside scope')
        if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Housing requires level99')
        if(item['metadata'],item['count'],item['group'])!=(0,1,4):raise ValueError('Housing original singleton contract')
        # Sample only after the real SQL writer and actor authorization.
        if now is None:now=int(time.time())
        if type(now)is not int or not 0<now<2**63-SECONDS:raise ValueError('Housing registration clock')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item,now=now)
        if item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Housing sealed contract')
        if template==PERMANENT_TEMPLATE:
            if now>=PERMANENT:raise ValueError('Housing registration outside current native date range')
            permanent_snapshot(db,uid,account_id)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(PERMANENT_TABLE,)).fetchone()is None:db.execute(PERMANENT_SQL)
            db.execute('INSERT INTO character_housing_permanent VALUES (?,?,?,?,?)',(uid,account_id,template,source_uid,now))
            expiry=PERMANENT
        else:
            expiry=lifetime(now+SECONDS)
            db.execute('CREATE TABLE IF NOT EXISTS character_housing_access (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template=136034),source_uid INTEGER NOT NULL CHECK(source_uid>0),registered_at INTEGER NOT NULL CHECK(registered_at>0),expires_at INTEGER NOT NULL CHECK(expires_at>registered_at))')
            db.execute('INSERT INTO character_housing_access VALUES (?,?,?,?,?,?)',(uid,account_id,TEMPLATE,source_uid,now,expiry))
        remove(db,uid,item);after=load_items(db,uid);positions=[(item['group'],item['slot'])]
        answer=[use_ack([(positions[0],None)],template,balance[0]),notice(expiry)]
        for event in answer:encode_event(event)
        guard(db)
        if not WRITES_ENABLED:raise ValueError('Housing access held before commit')
        snapshot(db,uid,account_id)
        _commit(db,operation,digest,uid,0x219,positions,before,after)
        return answer
