"""Exact owned bundle debit, three native grants and receipt in one SQL tx."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,struct
from els_server.domain.teacher_elixir_boxes import BOXES,admitted,definitions,validate_existing
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances

def recognizes(path,owner,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if row and row[0]in admitted():return True
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
            row=db.execute('SELECT before_json FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',(owner,0x196,operation)).fetchone()
            if row:
                prior=json.loads(row[0]);return any(i['uid']==uid and i['template']in BOXES for i in prior)
    return False

def open_box(path,owner,account_id,payload,operation,*,prepare):
    request=use_request(payload)
    if request.option not in (0,1) or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
        raise ValueError('Teacher bundle has no choice or bulk mode')
    owner,digest=_identity(owner,0x196,struct.pack('>Q',account_id)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_owner(db,owner,account_id);require_active_character(db,owner);prepare(db)
        prior=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if prior is not None:
            events=_updates(current_changes(db,operation,owner,0x196,prior,before))+result(balance['ed'])
            for e in events:encode_event(e)
            prepare(db);return events
        item=next((i for i in before if i['uid']==request.uid),None);validate_existing(item)
        if item['template']not in admitted():raise ValueError('Teacher bundle new uses closed')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item);require_unlocked(item)
        if item.get('sealed',False)or item.get('seal_used',0):raise ValueError('Teacher bundle seal state')
        if balance['revision']>=2**63-1:raise ValueError('Teacher bundle wallet revision')
        if item['count']==1:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',(owner,item['uid'],item['count'])).rowcount!=1:
            raise ValueError('Teacher bundle count changed')
        definition=definitions()[item['template']]
        grants=grant_items(db,[dict(template=e['template'],metadata=2,group=4,quantity=e['quantity'])for e in definition['entries']],owner)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({(item['group'],item['slot']),*((i['group'],i['slot'])for i in grants)})
        events=result(balance['ed'],[(p,current.get(p))for p in positions],[(e['template'],e['quantity'])for e in definition['entries']])
        for e in events:encode_event(e)
        prepare(db);require_owner(db,owner,account_id);require_active_character(db,owner)
        if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision=?',(owner,balance['revision'])).rowcount!=1:
            raise ValueError('Teacher bundle balance changed')
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
