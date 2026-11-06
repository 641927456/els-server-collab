"""Original owned official fixed boxes, one real SQL transaction."""
import hashlib,json,sqlite3,struct,uuid
from contextlib import closing
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.official_fixed_boxes import BOXES,outputs_for,plan_for
from els_server.domain.raid_reward_items import _issue_source
from els_server.storage import raid_economy_state as state


def authorize(db,owner,account_id,guard):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    if not db.in_transaction or not callable(guard)or guard()is not True:raise ValueError('Official fixed box action authority')
    require_active_character(db,owner);require_owner(db,owner,account_id)
    return True


def prepare_events(events):
    from els_server.protocol.protocol_codec import encode_event
    for e in events:encode_event(e)
    return events


def historical_box(path,owner,payload,operation):
    from els_server.protocol.ice_messages import use_request
    request=use_request(payload)
    with closing(sqlite3.connect(path,timeout=10))as db:
        if not state.exists(db,'inventory_action_receipts'):return None
        row=db.execute('SELECT request_hash,owner,kind,before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
        if row is None or row[1:3]!=(owner,0x196):return None
        candidates=[i['template']for i in json.loads(row[3])if i['uid']==request.uid and i['template']in BOXES]
        if len(candidates)!=1:return None
        expected=candidates[0]
        if _identity(owner,0x196,struct.pack('>i',expected)+payload,operation)[1]!=row[0]:raise ValueError('Conflicting official fixed box replay')
        return expected


def open_box(path,owner,template,payload,operation,account_id,guard):
    from els_server.protocol.ice_messages import use_request
    from els_server.protocol.cube_messages import result
    from els_server.storage.item_instances import remove
    from els_server.storage.seal_quests import load_character
    request=use_request(payload)
    if template not in BOXES or request.option or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
        raise ValueError('Official fixed box exact original request')
    owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,guard)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed']);prepare_events(events);authorize(db,owner,account_id,guard);return events
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=template or item['group']!=4:raise ValueError('Official fixed box exact owned instance')
        require_current(item);require_unlocked(item)
        from els_server.storage.luciel_state import active_state
        character=dict(load_character(db,owner,account_id),luciel_active_unit=active_state(db,owner)['active_unit'])
        outputs=outputs_for(template,character)
        plan=plan_for(template,character)
        op=str(uuid.uuid5(uuid.NAMESPACE_URL,'official-fixed-box:'+operation))
        source=dict(template=template,uid=item['uid'],owner=owner,operation=operation,owned_instance_sha256=hashlib.sha256(state.canonical(item).encode()).hexdigest())
        cap=_issue_source(db,owner,op,'box',source,plan,lambda writer:authorize(writer,owner,account_id,guard))
        position=(item['group'],item['slot'])
        if item['count']==1:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
        grants=grant_items(db,plan,owner,raid_reward_source=cap);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
        events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs]);prepare_events(events)
        if balance['revision']>=2**63-1:raise ValueError('Official fixed box balance revision overflow')
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after);authorize(db,owner,account_id,guard);return events
