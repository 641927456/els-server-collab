"""One true SQL transaction for one held coin, fee, material, XP and receipt."""
from contextlib import closing
import json,secrets,sqlite3
from els_server.domain.hunter_sphere_rules import FEE,plans,reward,advance
from els_server.domain.item_expiration import expired
from els_server.domain.item_locks import locked
from els_server.protocol.hunter_sphere_messages import request,acknowledgement
from els_server.protocol.profession_messages import ProfessionState
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items,validate_plan,InventoryFull
from els_server.storage.profession_state import require_owner,snapshot,replace
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.storage.bag_capacity import allowances

def _authorize(authorize):
    if not callable(authorize)or not authorize():raise ValueError('Sphere actor changed')

def _refresh(db,operation,owner,positions,items):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x705):raise ValueError('Sphere receipt owner/kind')
    try:
        before,after=(json.loads(v)for v in row[2:]);points=set(positions)
        if any(type(p)is not tuple or len(p)!=2 or any(type(v)is not int for v in p)for p in positions):raise ValueError('Sphere receipt positions')
        if not isinstance(before,list)or not isinstance(after,list)or any(not isinstance(i,dict)for i in before+after):raise ValueError('Sphere receipt history')
        affected={i['uid']for i in before+after if (i['group'],i['slot'])in points}
        if any(type(uid)is not int or not 0<uid<2**63 for uid in affected):raise ValueError('Sphere receipt UID')
    except (KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Sphere receipt format')from exc
    ordered=list(dict.fromkeys([*positions,*[(i['group'],i['slot'])for i in items if i['uid']in affected]]));current={(i['group'],i['slot']):i for i in items}
    return [(p,current.get(p))for p in ordered]

def _capacity(db,owner,items,options):
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
    limits=allowances(db,owner)
    for plan in options:
        validate_plan([plan]);group=plan['group']
        room=sum(TEMPLATE_MAX_STACKS[i['template']]-i['count']for i in items if i['template']==plan['template']and i['group']==group and i['metadata']==plan['metadata']and i.get('expires_at')is None)
        free=limits[group]-len({i['slot']for i in items if i['group']==group})
        if room+free*TEMPLATE_MAX_STACKS[plan['template']]<plan['quantity']:raise InventoryFull('Sphere output capacity')

def convert(path,owner,account_id,payload,operation,*,authorize,prepare_replay=None,randbelow=secrets.randbelow):
    coin=request(payload);owner,digest=_identity(owner,0x705,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_authorize(authorize)
        require_active_character(db,owner);require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner);growth=snapshot(db,owner,account_id);state=ProfessionState(**growth['state'])
        if old is not None:
            answer=[Event(0x201,kind=0x706,payload=acknowledgement(balance['ed'],changes=_refresh(db,operation,owner,old,before),state=state))]
            db.rollback();_authorize(authorize)
            if prepare_replay is not None:answer=prepare_replay(answer)
            for event in answer:encode_event(event)
            _authorize(authorize);return answer
        level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
        if level is None or type(level[0])is not int or level[0]<40:raise ValueError('Sphere level admission')
        next_state,xp=advance(state,coin)
        held=next((i for i in sorted(before,key=lambda i:(i['slot'],i['uid']))if i['template']==coin and i['group']==4 and not expired(i)and not locked(i)),None)
        if held is None:raise ValueError('Sphere held current unlocked coin required')
        if balance['ed']<FEE:raise ValueError('Sphere fee')
        _capacity(db,owner,before,plans(coin))
        selected=reward(coin,randbelow(100))
        ed=charge(db,owner,balance,FEE)
        if held['count']==1:remove(db,owner,held)
        else:
            cursor=db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',(owner,held['uid'],held['count']))
            if cursor.rowcount!=1:raise ValueError('Sphere coin changed')
        outputs=grant_items(db,[selected],owner)
        if xp:replace(db,owner,account_id,growth['revision'],next_state)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({(held['group'],held['slot'])}|{(i['group'],i['slot'])for i in outputs})
        answer=[Event(0x201,kind=0x706,payload=acknowledgement(ed,{selected['template']:selected['quantity']},[(p,current.get(p))for p in positions],next_state))]
        for event in answer:encode_event(event)
        _authorize(authorize);_commit(db,operation,digest,owner,0x705,positions,before,after);_authorize(authorize)
        return answer
