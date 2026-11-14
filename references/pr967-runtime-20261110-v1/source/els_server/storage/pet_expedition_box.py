"""Expedition box debit and one drawn grant in one SQL transaction."""
from pathlib import Path
from contextlib import closing
import secrets,sqlite3,struct
from els_server.domain.pet_expedition_box import BOXES,admitted,definitions,draw,validate_existing
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
    if not 0<uid<2**63:return False
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
            row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
            if row and row[0]in admitted():return True
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
                row=db.execute('SELECT before_json FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',
                    (owner,0x196,operation)).fetchone()
                if row:
                    import json
                    prior=json.loads(row[0]);return any(i['uid']==uid and i['template']in BOXES for i in prior)
    except(sqlite3.Error,ValueError,KeyError,TypeError):
        return False
    return False


def open_box(path,owner,account_id,payload,operation,*,prepare,randbelow=secrets.randbelow):
    request=use_request(payload)
    # selection_count0: the original client sends no choice, so an empty set
    # (or the0 placeholder) is the only valid request shape here.
    if (request.option not in(0,1)or request.choices not in((),(0,))
            or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3))):
        raise ValueError('Expedition box takes no choice and no bulk mode')
    owner,digest=_identity(owner,0x196,struct.pack('>Q',account_id)+payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_owner(db,owner,account_id);require_active_character(db,owner);prepare(db)
        prior=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if prior is not None:
            # The draw already has permanent consequences; replay only reprojects
            # the recorded positions and never rolls the pool a second time. The
            # granted rows come from the committed receipt, not a new search.
            import json
            row=db.execute('SELECT before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',
                (operation,)).fetchone()
            was={i['uid']for i in json.loads(row[0])}
            rewards=[(i['template'],i['count'])for i in json.loads(row[1])if i['uid']not in was]
            events=(_updates(current_changes(db,operation,owner,0x196,prior,before))
                +result(balance['ed'],rewards=tuple(rewards)))
            for e in events:encode_event(e)
            prepare(db);return events
        item=next((i for i in before if i['uid']==request.uid),None);validate_existing(item)
        if item['template']not in admitted():raise ValueError('Expedition box is outside the approved pool')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item);require_unlocked(item)
        if item.get('sealed',False)or item.get('seal_used',0):raise ValueError('Expedition box seal state')
        if balance['revision']>=2**63-1:raise ValueError('Expedition box wallet revision')
        if item['count']==1:
            from els_server.storage.item_instances import remove
            remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',
                (owner,item['uid'],item['count'])).rowcount!=1:
            raise ValueError('Expedition box count changed')
        entry=draw(item['template'],randbelow)
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        grants=grant_items(db,[dict(template=entry['template'],metadata=VERIFIED_TEMPLATES[entry['template']],
            group=TEMPLATE_BAG_GROUPS[entry['template']],quantity=entry['quantity'])],owner)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({(item['group'],item['slot']),*((i['group'],i['slot'])for i in grants)})
        events=result(balance['ed'],[(p,current.get(p))for p in positions],
            [(entry['template'],entry['quantity'])])
        for e in events:encode_event(e)
        prepare(db);require_owner(db,owner,account_id);require_active_character(db,owner)
        if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision=?',
                (owner,balance['revision'])).rowcount!=1:
            raise ValueError('Expedition box balance changed')
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
