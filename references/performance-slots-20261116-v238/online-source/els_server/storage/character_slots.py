"""Atomically consume an owned coupon and persist account-wide character slots."""
from contextlib import closing
from pathlib import Path
import hashlib,sqlite3,struct
from els_server.domain.character_slots import BASE_CAPACITY,MAX_CAPACITY,TICKETS,SlotsFull,validate_capacity,client_identity
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,owned_template
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked

SCHEMA='CREATE TABLE IF NOT EXISTS account_character_slots (account_id INTEGER PRIMARY KEY CHECK(account_id>0),capacity INTEGER NOT NULL CHECK(capacity BETWEEN 16 AND 72))'

def repair_existing_capacity(path):
    """Persist enough slots for retained legacy roles before admitting logins."""
    from els_server.storage.character_lifecycle import exists as has_lifecycle
    from els_server.storage.sqlite_timing import write_transaction
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,write_transaction(db):
        query='SELECT o.account_id,COUNT(*) FROM character_owners o'
        if has_lifecycle(db):
            query+=' LEFT JOIN character_lifecycle l ON l.uid=o.uid WHERE COALESCE(l.finalized_at,0)=0'
        query+=' GROUP BY o.account_id ORDER BY o.account_id'
        repairs=[]
        for account_id,count in db.execute(query):
            before=capacity(db,account_id)
            if count>before:
                repairs.append((account_id,before,validate_capacity(count)))
        if repairs:
            db.execute(SCHEMA)
            db.executemany('INSERT INTO account_character_slots VALUES (?,?) ON CONFLICT(account_id) DO UPDATE SET capacity=excluded.capacity',
                           ((account_id,after) for account_id,before,after in repairs))
        # Later character deletion must not shrink the recovered slots.
        return [dict(account_id=account_id,before=before,after=after) for account_id,before,after in repairs]

def capacity(db,account_id):
    if type(account_id)is not int or not 1<=account_id<2**63:raise ValueError('Account identity')
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_character_slots'").fetchone()
    row=db.execute('SELECT capacity FROM account_character_slots WHERE account_id=?',(account_id,)).fetchone() if exists else None
    return validate_capacity(row[0] if row else BASE_CAPACITY)

def snapshot(path,account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        return capacity(db,account_id)

def require_room(db,account_id,gain=1):
    current=capacity(db,account_id)
    if current+gain>MAX_CAPACITY:raise SlotsFull('Character slot expansion exceeds capacity')
    return current+gain

def use_coupon(path,owner,account_id,payload,operation_id):
    if not isinstance(payload,bytes) or len(payload)<8:return None
    item_uid=struct.unpack_from('>Q',payload)[0]
    if type(operation_id)is not str or not 1<=len(operation_id)<=160:raise ValueError('Character slot operation')
    digest=hashlib.sha256(str(owner).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):
            raise ValueError('Character slot coupon ownership')
        require_active_character(db,owner)
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_slot_use_receipts'").fetchone()
        old=db.execute('SELECT account_id,owner,request_hash,bag_group,slot FROM character_slot_use_receipts WHERE operation_id=?',(operation_id,)).fetchone() if exists else None
        if old:
            use_request(payload)
            if old[:3]!=(account_id,owner,digest):raise ValueError('Conflicting character slot retry')
            item=next((i for i in load_items(db,owner) if (i['group'],i['slot'])==old[3:]),None)
            ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
            event=use_ack([(old[3:],item)],ed=ed);encode_event(event)
            return [event]
        template=owned_template(db,owner,item_uid)
        if template not in TICKETS:return None
        use_request(payload)
        item=next(i for i in load_items(db,owner) if i['uid']==item_uid)
        if item['group']!=4:raise ValueError('Character slot coupon outside consumable inventory')
        require_current(item);require_unlocked(item)
        after=require_room(db,account_id,TICKETS[template])
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
        event=use_ack([((item['group'],item['slot']),remaining)],client_identity(template)[0],ed)
        encode_event(event)
        db.execute(SCHEMA)
        db.execute('INSERT INTO account_character_slots VALUES (?,?) ON CONFLICT(account_id) DO UPDATE SET capacity=excluded.capacity',(account_id,after))
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner))
        else:remove(db,owner,item)
        db.execute('CREATE TABLE IF NOT EXISTS character_slot_use_receipts (operation_id TEXT PRIMARY KEY,account_id INTEGER NOT NULL,owner INTEGER NOT NULL,request_hash TEXT NOT NULL,bag_group INTEGER NOT NULL,slot INTEGER NOT NULL)')
        db.execute('INSERT INTO character_slot_use_receipts VALUES (?,?,?,?,?,?)',(operation_id,account_id,owner,digest,item['group'],item['slot']))
        return [event]
