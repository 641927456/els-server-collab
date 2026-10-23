"""Finite normal9ED atomic transfer. Each ownlife retained as explicit nonretail compatibility."""
import json,sqlite3,time
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_reforge_rules import DEFAULT,state,expected_options
from els_server.domain.equipment_reforge_transfer_preflight import quote_request
from els_server.domain.equipment_reforge_transfer_rules import quote_pair
from els_server.domain.equipment_eligibility import inspect_eligibility
from els_server.protocol.equipment_reforge_transfer_messages import request,acknowledge
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_reforge import replace as replace_state,require_item
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.equipment_reforge_transfer_cost import read_owned_cost
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.manufacture_debits import apply_debits
from els_server.storage.npc_trade import balances,charge
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character


def _other_fields(item):
    item=dict(item);item.pop('reforge',None)
    groups=dict(item.pop('option_groups',{}));groups.pop('13',None)
    # An absent options container and a sole group13 represent the same other fields.
    if groups:item['option_groups']=groups
    return item


def _history(db,operation,owner,source_uid,target_uid):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x9ed):raise ValueError('Transfer receipt owner/kind')
    try:
        before,after=[json.loads(raw)for raw in row[2:]]
        if any(not isinstance(items,list)or any(not isinstance(i,dict)for i in items)for items in(before,after)):raise ValueError('Transfer receipt arrays')
        old={i['uid']:i for i in before};new={i['uid']:i for i in after}
        if len(old)!=len(before)or len(new)!=len(after):raise ValueError('Transfer receipt duplicate UID')
        source,target=old[source_uid],old[target_uid];a,b=new[source_uid],new[target_uid]
        previous=state(source['template'],source.get('reforge',DEFAULT));recipient=state(target['template'],target.get('reforge',DEFAULT))
        quote=quote_pair(source['template'],previous[0],target['template'],recipient[0],'normal')
        if (a.get('reforge',DEFAULT)!=[0,previous[1],0]
                or b.get('reforge',DEFAULT)!=[quote.target_new_level,recipient[1],0]
                or a.get('option_groups',{}).get('13')!=expected_options(source['template'],0)
                or b.get('option_groups',{}).get('13')!=expected_options(target['template'],quote.target_new_level)
                or _other_fields(source)!=_other_fields(a)or _other_fields(target)!=_other_fields(b)):
            raise ValueError('Transfer historical transition or sidecars')
        return source['template'],target['template']
    except (KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Transfer receipt history format')from exc


def perform(path,owner,payload,operation,*,account_id,authorize=None,now=None,encode=acknowledge):
    source_uid,target_uid,flag=request(payload)
    if flag!=0:raise ValueError('Ticket transfer is closed')
    owner,digest=_identity(owner,0x9ed,payload,operation)
    now=int(time.time())if now is None else now
    if type(now)is not int or now<0:raise ValueError('Transfer clock')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_active_character(db,owner);require_owner(db,owner,account_id)
        if authorize is not None and not authorize():raise ValueError('Obsolete transfer session')
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner);owned={i['uid']:i for i in before}
        if old is not None:
            historical=_history(db,operation,owner,source_uid,target_uid)
            source,target=owned.get(source_uid),owned.get(target_uid)
            if source is None or target is None or (source['template'],target['template'])!=historical:
                response=encode(source_uid,target_uid,balance['ed'],result=2005)
            else:response=encode(source_uid,target_uid,balance['ed'],current_changes(db,operation,owner,0x9ed,old,before))
            encode_event(response);return [response]
        source,target=owned.get(source_uid),owned.get(target_uid)
        require_item(source,equipment=True,now=now);require_item(target,equipment=True,now=now)
        actor=db.execute('SELECT unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
        if actor is None or any(not inspect_eligibility(i['template'],*actor)['template_requirements_met']for i in(source,target)):
            raise ValueError('Both templates require current actor ordinary eligibility')
        cost=read_owned_cost(db,owner,account_id,payload,now=now);quote=quote_request(payload,source,target)
        previous=state(source['template'],source.get('reforge',DEFAULT));recipient=state(target['template'],target.get('reforge',DEFAULT))
        source_next=[0,previous[1],0];target_next=[quote.target_new_level,recipient[1],0]
        requirements=dict(cost.materials);debits=[dict(uid=uid,quantity=n)for uid,n in cost.debits]
        affected={source_uid,target_uid,*[d['uid']for d in debits]};positions=[(i['group'],i['slot'])for i in before if i['uid']in affected]
        ed=charge(db,owner,balance,cost.ed_fee)
        apply_debits(db,owner,account_id,requirements,debits,now=now)
        for item,prior,updated in((source,previous,source_next),(target,recipient,target_next)):
            groups=item.get('option_groups',{})
            replace_options(db,owner,item['uid'],groups,{**groups,'13':expected_options(item['template'],updated[0])})
            replace_state(db,owner,item['uid'],prior,updated)
        after=load_items(db,owner);change=current_changes_after(after,positions,affected)
        response=encode(source_uid,target_uid,ed,change);encode_event(response)
        _commit(db,operation,digest,owner,0x9ed,positions,before,after)
        return [response]


def current_changes_after(items,positions,affected):
    # Reuse the current reforge refresh primitive, also used by existing8D5/8D9.
    from els_server.storage.equipment_reforge import changes
    return changes(items,positions,affected)
