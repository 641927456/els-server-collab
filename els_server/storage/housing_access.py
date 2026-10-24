"""Finite first-use136034 seven-day access; no room, furniture or renewal writer."""
import sqlite3,time
from pathlib import Path
from contextlib import closing
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.housing_access_messages import lifetime,notice
from els_server.protocol.protocol_codec import encode_event

WRITES_ENABLED=True
TABLE='character_housing_access'
TEMPLATE=136034
SECONDS=7*24*60*60

def exists(db):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()is not None

def owner(db,uid,account_id):
    if type(account_id)is not int or not 0<account_id<2**63:raise ValueError('Housing account identity')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Housing owner mismatch')

def snapshot(db,uid,account_id):
    owner(db,uid,account_id)
    if not exists(db):return None
    row=db.execute('SELECT account_id,template,source_uid,registered_at,expires_at FROM character_housing_access WHERE owner=?',(uid,)).fetchone()
    if row is None:return None
    if(row[0]!=account_id or row[1]!=TEMPLATE or any(type(v)is not int or not 0<v<2**63 for v in row[2:])or row[4]-row[3]!=SECONDS):raise ValueError('Housing access integrity')
    lifetime(row[4]);return dict(template=row[1],source_uid=row[2],registered_at=row[3],expires_at=row[4])

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
        if old is None and(item is None or item['template']!=TEMPLATE):return None
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None or type(balance[0])is not int or not 0<=balance[0]<2**63:raise ValueError('Housing ED read integrity')
        if old is not None:
            if state is None or state['source_uid']!=source_uid:raise ValueError('Housing receipt access missing')
            changes=current_changes(db,operation,uid,0x219,old,before)
            answer=[use_ack(changes,TEMPLATE,balance[0]),notice(state['expires_at'])]
            for event in answer:encode_event(event)
            guard(db);return answer
        if not WRITES_ENABLED:raise ValueError('Housing access writer held')
        if state is not None:raise ValueError('Housing renewal is outside first-use scope')
        if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Housing requires level99')
        if(item['metadata'],item['count'],item['group'])!=(0,1,4):raise ValueError('Housing original singleton contract')
        # Sample only after the real SQL writer and actor authorization.
        if now is None:now=int(time.time())
        if type(now)is not int or not 0<now<2**63-SECONDS:raise ValueError('Housing registration clock')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item)
        expiry=lifetime(now+SECONDS)
        db.execute('CREATE TABLE IF NOT EXISTS character_housing_access (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template=136034),source_uid INTEGER NOT NULL CHECK(source_uid>0),registered_at INTEGER NOT NULL CHECK(registered_at>0),expires_at INTEGER NOT NULL CHECK(expires_at>registered_at))')
        db.execute('INSERT INTO character_housing_access VALUES (?,?,?,?,?,?)',(uid,account_id,TEMPLATE,source_uid,now,expiry))
        remove(db,uid,item);after=load_items(db,uid);positions=[(item['group'],item['slot'])]
        answer=[use_ack([(positions[0],None)],TEMPLATE,balance[0]),notice(expiry)]
        for event in answer:encode_event(event)
        guard(db)
        if not WRITES_ENABLED:raise ValueError('Housing access held before commit')
        snapshot(db,uid,account_id)
        _commit(db,operation,digest,uid,0x219,positions,before,after)
        return answer
