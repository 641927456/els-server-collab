"""Atomic owned elixir consumption and original absolute-end persistence.

One row owns one mutually exclusive ordinary group. Other actor effects are
not ledger entries. No EP offer, client effect, damage or countdown is made.
"""
from contextlib import closing
import json,sqlite3,struct,time
from els_server.domain.elixir_items import ITEMS,catalog
from els_server.protocol.world_buff_messages import request
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes

def _exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def _owner(db,owner,account_id):
    from els_server.storage.profession_state import require_owner
    from els_server.storage.character_lifecycle import states
    require_owner(db,owner,account_id)
    state=states(db,(owner,)).get(owner,{})
    if state.get('requested_at') or state.get('finalized_at'):raise ValueError('Unavailable elixir actor')

def _clock(now):
    now=int(time.time())if now is None else now
    if type(now)is not int or not 1<=now<2**31-7200:raise ValueError('Elixir epoch bounds')
    return now

def _state(db,owner,now):
    if not _exists(db,'world_elixir_state'):return dict(owner=owner,revision=0,rows=[])
    r=db.execute('SELECT revision,template,source_uid,starts_at,ends_at,operation_id FROM world_elixir_state WHERE owner=?',(owner,)).fetchone()
    if r is None:return dict(owner=owner,revision=0,rows=[])
    revision,template,source,starts,ends,operation=r
    if type(revision)is not int or not 1<=revision<2**63:raise ValueError('Elixir revision')
    if template==0:
        if (source,starts,ends,operation)!=(0,0,0,''):raise ValueError('Elixir empty state')
        rows=[]
    else:
        rule=catalog().get(template)
        if not rule or any(type(v)is not int for v in(source,starts,ends))or not 0<source<2**63 or not 1<=starts<ends<2**31 or ends-starts!=rule['period_seconds']:raise ValueError('Unqualified elixir state')
        _source(db,operation,owner,source,template)
        rows=[dict(owner=owner,template=template,source_uid=source,start=starts,end=ends)]if now<ends else []
    return dict(owner=owner,revision=revision,rows=rows)

def snapshot(path,owner,account_id,*,now=None):
    now=_clock(now)
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');_owner(db,owner,account_id);return _state(db,owner,now)

def _ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS world_elixir_state(owner INTEGER PRIMARY KEY REFERENCES characters(uid),revision INTEGER NOT NULL CHECK(revision>0),template INTEGER NOT NULL,source_uid INTEGER NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL)')

def _source(db,operation,owner,source,template):
    if not isinstance(operation,str)or not 1<=len(operation)<=160 or not _exists(db,'inventory_action_receipts'):raise ValueError('Elixir source receipt missing')
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x219):raise ValueError('Elixir source receipt missing')
    try:
        before,after=(json.loads(v)for v in row[2:])
        if not isinstance(before,list)or len(before)!=1 or not isinstance(before[0],dict):raise ValueError('Elixir source receipt missing')
        item=before[0]
        if (item['uid'],item['template'],item['group'],item['metadata'])!=(source,template,4,catalog()[template]['metadata'])or type(item['count'])is not int or item['count']<1:raise ValueError('Elixir source receipt missing')
        expected=[dict(item,count=item['count']-1)]if item['count']>1 else []
        if after!=expected:raise ValueError('Elixir source receipt missing')
    except(KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Elixir source receipt missing')from exc

def candidate(path,owner,payload,operation):
    # Read-only finite interception. No generic 219 interpretation or mutation.
    if not isinstance(payload,bytes)or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(path,timeout=10))as db:
        item=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if item and item[0]in ITEMS:return True
        return bool(_exists(db,'inventory_action_receipts')and db.execute('SELECT 1 FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',(owner,0x219,operation)).fetchone())

def use(path,owner,account_id,payload,operation,prepare,*,now=None):
    item_uid,additional=request(payload)
    owner,digest=_identity(owner,0x219,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=_clock(now);_owner(db,owner,account_id)
        old=_previous(db,operation,digest)
        from els_server.storage.inventory_state import load_items
        from els_server.storage.npc_trade import balances
        items=load_items(db,owner);ed=balances(db,owner)['ed'];state=_state(db,owner,now)
        if old is not None:
            receipt=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
            try:template=json.loads(receipt[0])[0]['template']
            except(TypeError,IndexError,KeyError,json.JSONDecodeError)as exc:raise ValueError('Elixir source receipt missing')from exc
            if template not in ITEMS:raise ValueError('Elixir source receipt missing')
            _source(db,operation,owner,item_uid,template)
            events=[use_ack(current_changes(db,operation,owner,0x219,old,items),ed=ed)]+prepare(db,state,items)
            for event in events:encode_event(event)
            return dict(events=events,state=state,replayed=True,result=0)
        item=next((i for i in items if i['uid']==item_uid),None)
        if item is None or item['template']not in ITEMS or(item['group'],item['metadata'])!=(4,catalog()[item['template']]['metadata'])or item.get('sealed',False):raise ValueError('Owned elixir required')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item,now=now)
        level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
        if level<catalog()[item['template']].get('minimum_level',0):raise ValueError('Elixir level requirement')
        if additional==1 and state['rows']:
            # No DDL/receipt/expiry cleanup: the original confirmation is 0-write.
            return dict(events=[use_ack(result=403)],state=state,replayed=False,result=403)
        if state['revision']>=2**63-1:raise ValueError('Elixir revision overflow')
        after=dict(item,count=item['count']-1)if item['count']>1 else None
        new=dict(owner=owner,revision=state['revision']+1,rows=[dict(owner=owner,template=item['template'],source_uid=item_uid,start=now,end=now+catalog()[item['template']]['period_seconds'])])
        remaining=[after if i['uid']==item_uid else i for i in items if i['uid']!=item_uid or after]
        # Preflight the exact ACK and canonical full-set notification inside
        # this transaction. Encoder/profile failure cannot consume a stack.
        events=[use_ack([((item['group'],item['slot']),after)],item['template'],ed)]+prepare(db,new,remaining)
        for event in events:encode_event(event)
        _ensure(db)
        if after:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(item_uid,owner,item['count'])).rowcount!=1:raise ValueError('Elixir stack changed')
        else:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        db.execute('INSERT INTO world_elixir_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,template=excluded.template,source_uid=excluded.source_uid,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(owner,new['revision'],item['template'],item_uid,now,new['rows'][0]['end'],operation))
        _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],[item],[after]if after else [])
        return dict(events=events,state=new,replayed=False,result=0)

def expire(path,owner,account_id,prepare,*,now=None):
    now=_clock(now)
    # The ordinary idle path is read-only; do not acquire a writer every second.
    with closing(sqlite3.connect(path,timeout=10))as probe:
        probe.execute('BEGIN');_owner(probe,owner,account_id)
        if not _exists(probe,'world_elixir_state'):return None
        due=probe.execute('SELECT 1 FROM world_elixir_state WHERE owner=? AND template!=0 AND ends_at<=?',(owner,now)).fetchone()
        if not due:return None
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');_owner(db,owner,account_id);state=_state(db,owner,now)
        if not state['revision']or state['rows']:return None
        old=db.execute('SELECT template,ends_at FROM world_elixir_state WHERE owner=?',(owner,)).fetchone()
        if not old or not old[0]or now<old[1]:return None
        if state['revision']>=2**63-1:raise ValueError('Elixir revision overflow')
        state=dict(state,revision=state['revision']+1);events=prepare(db,state,None)
        for event in events:encode_event(event)
        db.execute("UPDATE world_elixir_state SET revision=?,template=0,source_uid=0,starts_at=0,ends_at=0,operation_id='' WHERE owner=?",(state['revision'],owner))
        return dict(events=events,state=state)

def notice(path,owner,account_id,prepare,*,now=None):
    now=_clock(now)
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');_owner(db,owner,account_id);state=_state(db,owner,now)
        return dict(state=state,events=prepare(db,state,None)if state['revision']else [])
