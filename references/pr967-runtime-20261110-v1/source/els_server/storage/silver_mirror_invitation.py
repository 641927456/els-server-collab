"""Existing-owned Division145 invitation; restore only an exhausted week."""
import json,sqlite3,struct,time
from contextlib import closing
from els_server.domain.silver_mirror_catalog import INVITATIONS
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.npc_trade import balances
from els_server.storage import silver_mirror_state as store

def candidate(path,owner,payload,operation):
    if not isinstance(payload,bytes)or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(path,timeout=10))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if row and row[0]in INVITATIONS:return True
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():return False
        return bool(db.execute('SELECT 1 FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',(owner,0x219,operation)).fetchone())

def use(path,owner,account_id,payload,operation,authorize,prepare):
    uid=use_request(payload);owner,digest=_identity(owner,0x219,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        store.guard(db,owner,account_id,authorize)
        now=time.time();state=store.read(db,owner,now)
        prior=_previous(db,operation,digest);items=load_items(db,owner);balance=balances(db,owner)
        if prior is not None:
            r=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
            before=json.loads(r[2]);after=json.loads(r[3])
            if r[:2]!=(owner,0x219)or len(before)!=1 or(before[0]['uid'],before[0]['template'])not in[(uid,t)for t in INVITATIONS]:raise ValueError('Mirror invitation source receipt')
            expected=[dict(before[0],count=before[0]['count']-1)]if before[0]['count']>1 else []
            if after!=expected:raise ValueError('Mirror invitation exact consumed source')
            events=[use_ack(current_changes(db,operation,owner,0x219,prior,items),before[0]['template'],balance['ed']),*prepare(db)]
        else:
            item=next((i for i in items if i['uid']==uid),None)
            if not item or item['template']not in INVITATIONS or(item['group'],item['metadata'])!=(4,2)or item.get('sealed'):raise ValueError('Owned Mirror invitation required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            require_current(item,now=int(now));require_unlocked(item,now=int(now))
            if state['remaining']!=0:raise ValueError('Mirror weekly rewards are not exhausted')
            after=dict(item,count=item['count']-1)if item['count']>1 else None
            if after:
                if db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',(owner,uid,item['count'])).rowcount!=1:raise ValueError('Mirror invitation source changed')
            else:
                from els_server.storage.item_instances import remove
                remove(db,owner,item)
            store.save(db,dict(state,remaining=5,revision=state['revision']+1))
            events=[use_ack([((item['group'],item['slot']),after)],item['template'],balance['ed']),*prepare(db)]
            for event in events:encode_event(event)
            require_current(item);require_unlocked(item)
            _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],[item],[after]if after else [])
        for event in events:encode_event(event)
        if store.clock(time.time())[1]!=state['week']:raise ValueError('Mirror invitation crossed weekly reset')
        store.guard(db,owner,account_id,authorize)
        return events
