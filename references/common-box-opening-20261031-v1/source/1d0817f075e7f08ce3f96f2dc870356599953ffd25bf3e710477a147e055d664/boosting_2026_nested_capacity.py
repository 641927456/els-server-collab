"""Open six tickets, then consume each for durable capacity, all atomically."""
import sqlite3,struct
from contextlib import closing
from els_server.domain.boosting_2026_nested_capacity import BOX,POLICY,items
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request as cube_request
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items,owned_template
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.storage.bag_capacity import allowances,expand

def open_box(path,owner,payload,operation):
    if not items():raise ValueError('Nested capacity is not registered')
    request=cube_request(payload)
    if request.option not in (0,1) or request.choices or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3)):raise ValueError('Nested capacity box has no choices')
    owner,digest=_identity(owner,0x196,struct.pack('>i',BOX)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prior=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if prior is not None:return _updates(current_changes(db,operation,owner,0x196,prior,before))+result(balance['ed'])
        source=next((i for i in before if i['uid']==request.uid),None)
        if source is None or source['template']!=BOX or source['group']!=4:raise ValueError('Owned nested capacity box required')
        require_current(source);require_unlocked(source)
        if balance['revision']>=2**63-1:raise ValueError('Nested capacity revision overflow')
        position=(source['group'],source['slot'])
        if source['count']==1:remove(db,owner,source)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source['uid'],owner))
        grants=grant_items(db,[dict(template=t,metadata=2,group=4,quantity=1) for t in items()],owner)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({position,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(t,1) for t in items()])
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events

def effect_exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity2026_capacity_receipts'").fetchone())

def use_ticket(path,owner,payload,operation):
    if not items():return None
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        effect=db.execute('SELECT owner,item_uid,template,bag_group,before_capacity,after_capacity,policy FROM activity2026_capacity_receipts WHERE operation_id=?',(operation,)).fetchone() if effect_exists(db) else None
        candidate_uid=struct.unpack_from('>Q',payload)[0] if len(payload)>=8 else 0
        rule=items().get(owned_template(db,owner,candidate_uid))
        if effect is None and rule is None:return None
        before=load_items(db,owner);item=next((i for i in before if i['uid']==candidate_uid),None)
        uid=use_request(payload)
        owner,digest=_identity(owner,0x219,payload,operation);prior=_previous(db,operation,digest);balance=balances(db,owner)
        if effect is not None:
            if (prior is None or effect[0:2]!=(owner,uid) or effect[2] not in items() or effect[3]!=items()[effect[2]]['capacity_group']
                or effect[5]!=effect[4]+8 or effect[6]!=POLICY or allowances(db,owner)[effect[3]]<effect[5]):raise ValueError('Nested capacity receipt/effect mismatch')
            current={(i['group'],i['slot']):i for i in before};positions=sorted(set(prior)|({(item['group'],item['slot'])} if item else set()))
            return dict(replayed=True,events=[use_ack([(p,current.get(p)) for p in positions],ed=balance['ed'])])
        if prior is not None:raise ValueError('Nested capacity effect receipt missing')
        if item['group']!=4:raise ValueError('Owned capacity ticket in consumable bag required')
        require_current(item);require_unlocked(item)
        if balance['revision']>=2**63-1:raise ValueError('Capacity ticket revision overflow')
        group=rule['capacity_group'];old=allowances(db,owner)[group];new=expand(db,owner,rule['canonical_product'],1)
        position=(item['group'],item['slot'])
        if item['count']==1:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(uid,owner))
        after=load_items(db,owner);current=next((i for i in after if (i['group'],i['slot'])==position),None)
        from els_server.domain.bag_capacity import expansion_notice
        notice=expansion_notice(dict(bag_capacities={group:old}),dict(bag_capacities={group:new}))
        events=[use_ack([(position,current)],item['template'],balance['ed']),notice]
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x219,[position],before,after)
        db.execute('''CREATE TABLE IF NOT EXISTS activity2026_capacity_receipts (
          operation_id TEXT PRIMARY KEY REFERENCES inventory_action_receipts(operation_id),
          owner INTEGER NOT NULL,item_uid INTEGER NOT NULL,template INTEGER NOT NULL,bag_group INTEGER NOT NULL,
          before_capacity INTEGER NOT NULL,after_capacity INTEGER NOT NULL,policy TEXT NOT NULL)''')
        db.execute('INSERT INTO activity2026_capacity_receipts VALUES(?,?,?,?,?,?,?,?)',(operation,owner,uid,item['template'],group,old,new,POLICY))
        return dict(replayed=False,events=events)
