"""One SQL transaction for one potion, actual shared life and original notices."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,struct
from els_server.domain.life_potions_existing import TEMPLATES,admitted,definitions,request,validate_existing,read_existing
from els_server.storage import life_stamina as life
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_ack
from els_server.protocol.fishing_messages import life_notice
from els_server.protocol.protocol_codec import encode_event

def recognizes(path,owner,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if row and row[0]in admitted():return True
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
            row=db.execute('SELECT before_json FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',(owner,0x219,operation)).fetchone()
            if row:return any(i['uid']==uid and i['template']in TEMPLATES for i in json.loads(row[0]))
    return False

def perform(path,owner,account_id,payload,operation,*,prepare):
    uid=request(payload);owner,digest=_identity(owner,0x219,struct.pack('>Q',account_id)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');life.owner(db,owner,account_id);prepare(db)
        prior=_previous(db,operation,digest);items=load_items(db,owner)
        balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('Life potion wallet missing')
        state=life.snapshot(db,owner,account_id)
        if prior is not None:
            events=[use_ack(current_changes(db,operation,owner,0x219,prior,items),ed=balance[0]),life_notice(state['current'],show_delta=False)]
            for e in events:encode_event(e)
            prepare(db);return events
        item=next((i for i in items if i['uid']==uid),None);validate_existing(item)
        if item['template']not in admitted():raise ValueError('Life potion new uses closed')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item);require_unlocked(item)
        if item.get('sealed',False)or item.get('seal_used',0):raise ValueError('Life potion seal state')
        if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):raise ValueError('Life potion level99 required')
        if not life.exists(db)or state['current']>=state['maximum']:raise ValueError('Life already full or original login missing')
        current=min(state['maximum'],state['current']+definitions()[item['template']]['restore'])
        after=read_existing(dict(item,count=item['count']-1))if item['count']>1 else None
        events=[use_ack([((item['group'],item['slot']),after)],item['template'],balance[0]),life_notice(current,show_delta=True)]
        for e in events:encode_event(e)
        if after:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(uid,owner,item['count'])).rowcount!=1:raise ValueError('Life potion count changed')
        else:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        if db.execute('UPDATE account_life_stamina SET current=? WHERE account=? AND current=? AND maximum=?',(current,account_id,state['current'],state['maximum'])).rowcount!=1:
            raise ValueError('Life potion account state changed')
        prepare(db);life.owner(db,owner,account_id)
        _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],[item],[after]if after else[])
        return events
