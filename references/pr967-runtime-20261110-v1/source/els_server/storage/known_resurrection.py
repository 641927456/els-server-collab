"""Known-source role counter only; no daily/free/cash allocation policy.

Read paths never initialize a table. Owned190556 credit and current-life debit
are committed with their own proof, without a server HP or animation model.
"""
from contextlib import closing
from pathlib import Path
import sqlite3,struct,uuid
from els_server.storage.character_schema import character_uid
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.storage.resurrection_counter import count,snapshot,MAX_COUNT

BOX=190556
GAIN=10
def _authorize(db,owner,account_id,guard):
    if not db.in_transaction:raise ValueError('Resurrection transaction required')
    require_active_character(db,owner)
    if account_id is not None:require_owner(db,owner,account_id)
    if not callable(guard):raise ValueError('Resurrection current context guard required')
    guard()

def _set(db,owner,value):
    if type(value) is not int or not 0<=value<=MAX_COUNT:raise ValueError('Known resurrection count bound')
    db.execute('''CREATE TABLE IF NOT EXISTS known_resurrection_stones (
        owner INTEGER PRIMARY KEY,count INTEGER NOT NULL CHECK(count>=0 AND count<=2147483647))''')
    db.execute('INSERT INTO known_resurrection_stones VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET count=excluded.count',(owner,value))

def open_box(path,owner,payload,operation,*,account_id,guard):
    from els_server.protocol.ice_messages import use_request
    from els_server.protocol.known_resurrection import box_result
    request=use_request(payload)
    if request.option not in (0,1) or request.choices or any(v not in (0,1)for v in(request.flag1,request.flag2,request.flag3)):
        raise ValueError('Known resurrection box use mode')
    owner,digest=_identity(owner,0x196,struct.pack('>i',BOX)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        _authorize(db,owner,account_id,guard)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        current=count(db,owner)
        if old is not None:
            changes=current_changes(db,operation,owner,0x196,old,before)
            answer=box_result(balance['ed'],current,changes)
            _authorize(db,owner,account_id,guard)
            return answer
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or (item['template'],item['metadata'],item['group'],item['count'])!=(BOX,2,4,1):
            raise ValueError('Known resurrection box instance does not belong to actor')
        require_current(item);require_unlocked(item)
        if current>MAX_COUNT-GAIN or balance['revision']>=2**63-1:raise ValueError('Known resurrection credit overflow')
        source=(item['group'],item['slot']);remove(db,owner,item)
        _set(db,owner,current+GAIN)
        after=load_items(db,owner);positions=[source]
        answer=box_result(balance['ed'],current+GAIN,[(source,None)])
        _authorize(db,owner,account_id,guard)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return answer

def historical_box(path,owner,payload,operation):
    """Read-only classification after the owned instance was consumed.

    A retry is identified by its exact committed hash and source190556 history,
    never by a mutable preview hint, missing UID, or a different current item.
    """
    owner,digest=_identity(owner,0x196,struct.pack('>i',BOX)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():return False
        row=db.execute('SELECT request_hash,owner,kind,before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
        if row is None:return False
        if row[:3]!=(digest,owner,0x196):return False
        import json
        before=json.loads(row[3])
        from els_server.protocol.ice_messages import use_request
        uid=use_request(payload).uid
        return any(i.get('uid')==uid and i.get('template')==BOX for i in before)

def spend(path,owner,payload,operation,run,life,*,account_id,guard,dungeon=30000,position=-1,prepare=None,limit=None):
    owner=character_uid(owner)
    if type(run) is not str or str(uuid.UUID(run))!=run or uuid.UUID(run).version!=4:
        raise ValueError('Known resurrection run identity')
    if type(life) is not int or not 1<=life<2**63:raise ValueError('Known resurrection life identity')
    owner,digest=_identity(owner,0x160,run.encode()+struct.pack('>Q',life)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        _authorize(db,owner,account_id,guard)
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_resurrection_spends'").fetchone():
            old=db.execute('SELECT request_hash,owner,run,life FROM known_resurrection_spends WHERE operation_id=?',(operation,)).fetchone()
            if old is not None:
                if old!=(digest,owner,run,life):raise ValueError('Conflicting known resurrection spend retry')
                return dict(count=count(db,owner),replayed=True)
            if db.execute('SELECT 1 FROM known_resurrection_spends WHERE owner=? AND run=? AND life=?',(owner,run,life)).fetchone():
                raise ValueError('Current life resurrection already committed')
        if limit is not None:
            if type(limit)is not int or limit!=1:raise ValueError('Finite original revival cap')
            spent=db.execute('SELECT COUNT(*) FROM known_resurrection_spends WHERE owner=? AND run=?',(owner,run)).fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_resurrection_spends'").fetchone()else 0
            if spent>=limit:raise ValueError('Original per-run resurrection cap reached')
        current=count(db,owner)
        if current<=0:raise ValueError('No known source resurrection stones')
        from els_server.protocol.known_resurrection import continuation
        # Validate complete native replies before committing the economic change.
        answer=continuation(owner,current-1,dungeon=dungeon,position=position)
        prepared=prepare(answer) if prepare is not None else None
        _authorize(db,owner,account_id,guard)
        _set(db,owner,current-1)
        db.execute('''CREATE TABLE IF NOT EXISTS known_resurrection_spends (
            operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,
            run TEXT NOT NULL,life INTEGER NOT NULL,UNIQUE(owner,run,life))''')
        db.execute('INSERT INTO known_resurrection_spends VALUES (?,?,?,?,?)',(operation,digest,owner,run,life))
        return dict(count=current-1,replayed=False,events=answer,prepared=prepared)
