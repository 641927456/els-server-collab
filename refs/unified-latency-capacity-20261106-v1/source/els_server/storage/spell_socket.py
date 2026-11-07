"""Paid native mode2 preview; mode4 applies that exact saved option once."""
from contextlib import closing
from pathlib import Path
import json,secrets,sqlite3,struct,time
from els_server.domain import spell_socket_rules as rules
from els_server.domain.equipment_spell_rules import capacity
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.spell_socket_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import spell_socket_pending as pending
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.npc_trade import balances,charge

def target(item,group,slot,moment):
    if item is None or item['count']!=1 or item['group']not in(1,9)or item.get('identified')is False or item.get('sealed'):
        raise ValueError('Owned identified mystic weapon required')
    require_current(item,now=moment);require_unlocked(item,now=moment)
    if not 0<=slot<capacity(item,group):raise ValueError('Mystic slot exceeds current native capacity')

def active(db,owner,item,moment):
    row=pending.get(db,owner)
    if row is None or item is None or row['item_uid']!=item['uid']:return None
    target(item,row['socket_group'],row['slot'],moment)
    material=rules.material(row['material_id']);rules.validate_option(row['material_id'],row['option_id'])
    if material['socket_group']!=row['socket_group']or row['basis_json']!=pending.basis(item):raise ValueError('Mystic paid target changed')
    if type(row['created_at'])is not int or not 0<=row['created_at']<=moment:raise ValueError('Mystic paid clock')
    original=struct.pack('>QIiIiQBiB',row['item_uid'],1,row['socket_group'],1,row['slot'],row['source_uid'],0,2,0)
    _,digest=_identity(owner,0x6e7,original,row['generation'])
    receipt=db.execute('SELECT owner,kind,request_hash,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(row['generation'],)).fetchone()
    if receipt is None or receipt[:3]!=(owner,0x6e7,digest):raise ValueError('Mystic paid generation receipt missing')
    before={i['uid']:i for i in json.loads(receipt[3])};after={i['uid']:i for i in json.loads(receipt[4])}
    source=before.get(row['source_uid']);remaining=after.get(row['source_uid'])
    if (before.get(item['uid'])!=item or after.get(item['uid'])!=item or source is None
        or(source['template'],source['metadata'],source['group'])!=(row['material_id'],material['metadata'],4)
        or(remaining!=dict(source,count=source['count']-1)if source['count']>1 else remaining is not None)):
        raise ValueError('Mystic paid original stone/target receipt')
    return row

def perform(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id,authorize=lambda db:None,now=time.time,encode=acknowledgement):
    uid,group,slot,source_uid,mode=request(payload);owner,digest=_identity(owner,0x6e7,payload,operation)
    def authority(db):
        require_owner(db,owner,account_id);require_active_character(db,owner);authorize(db)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authority(db)
        old=_previous(db,operation,digest);before=load_items(db,owner);by_uid={i['uid']:i for i in before};item=by_uid.get(uid);balance=balances(db,owner)
        moment=int(now())
        if not 0<=moment<2**40:raise ValueError('Mystic clock')
        if old is not None:
            option=0;result=0
            if mode==2:
                value=active(db,owner,item,moment)
                if value is None or value['generation']!=operation:result=2005
                else:option=value['option_id']
            event=encode(uid,balance['ed'],current_changes(db,operation,owner,0x6e7,old,before),mode=mode,option=option,result=result)
            encode_event(event);authority(db);return [event]
        if mode==2:
            target(item,group,slot,moment);source=by_uid.get(source_uid)
            if source is None or source['group']!=4 or source.get('sealed')or source.get('identified')is False:raise ValueError('Owned current mystic stone required')
            rule=rules.material(source['template'])
            if rule['socket_group']!=group or source['metadata']!=rule['metadata']:raise ValueError('Mystic source color/metadata')
            require_current(source,now=moment);require_unlocked(source,now=moment)
            fee=rules.catalog()['fee_ed']
            if balance['ed']<fee or balance['revision']>=2**63-1:raise ValueError('Mystic insufficient ED/revision')
            option=rules.draw(source['template'],randbelow);ed=charge(db,owner,balance,fee)
            from els_server.storage.manufacture_debits import apply_debits
            apply_debits(db,owner,account_id,{source['template']:1},[dict(uid=source_uid,quantity=1)],now=moment)
            pending.ensure(db)
            db.execute('INSERT INTO equipment_spell_pending VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET item_uid=excluded.item_uid,generation=excluded.generation,socket_group=excluded.socket_group,slot=excluded.slot,option_id=excluded.option_id,material_id=excluded.material_id,source_uid=excluded.source_uid,basis_json=excluded.basis_json,created_at=excluded.created_at',
                (owner,uid,operation,group,slot,option,source['template'],source_uid,pending.basis(item),moment))
            positions=[(source['group'],source['slot'])];expected=item
        else:
            value=active(db,owner,item,moment)
            if value is None:raise ValueError('Mystic apply requires original paid preview')
            from els_server.storage.equipment_options import replace
            group=value['socket_group'];slot=value['slot'];previous=item.get('option_groups',{});vector=list(previous.get(str(group),[]))
            vector+=[0]*max(0,capacity(item,group)-len(vector));vector[slot]=value['option_id'];updated={**previous,str(group):vector}
            replace(db,owner,uid,previous,updated);pending.cancel(db,owner,[uid]);option=0;ed=balance['ed'];positions=[(item['group'],item['slot'])];expected={**item,'option_groups':updated}
        after=load_items(db,owner)
        if next((i for i in after if i['uid']==uid),None)!=expected:raise ValueError('Mystic target changed in original writer')
        current={(i['group'],i['slot']):i for i in after}
        event=encode(uid,ed,[(p,current.get(p))for p in positions],mode=mode,option=option)
        encode_event(event);authority(db);_commit(db,operation,digest,owner,0x6e7,positions,before,after);authority(db)
        return [event]
