"""Atomic current smith single-hammer enhancement and fallback XP; no new schema."""
import secrets,sqlite3
from contextlib import closing
from els_server.domain.blacksmith_enhancement_rules import quote,outcome,STONES
from els_server.domain.profession_growth import advance_blacksmith
from els_server.domain.item_expiration import expired
from els_server.domain.item_locks import locked
from els_server.protocol.blacksmith_enhancement_messages import options,acknowledgement,hammer_selection
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.profession_messages import ProfessionState,level_update
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner,snapshot,replace as replace_profession
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.storage.equipment_enhancement import replace

def _authorize(authorize):
    if not callable(authorize) or not authorize():raise ValueError('Smith current actor changed')

def _allocate(items,templates,quantity,used,group):
    result=[]
    for template in templates:
        for item in sorted(items,key=lambda i:(i['slot'],i['uid'])):
            if item['template']!=template or item['group']!=group or expired(item) or locked(item):continue
            amount=min(quantity,item['count']-used.get(item['uid'],0))
            if amount>0:
                used[item['uid']]=used.get(item['uid'],0)+amount;result.append((item,amount));quantity-=amount
            if not quantity:return result
    raise ValueError('Insufficient current unlocked smith materials')

def enhance(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id,authorize,prepare_replay=None):
    uid,mode,context=options(payload);owner,digest=_identity(owner,0x5ff,payload,operation)
    hammer=hammer_selection(payload)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        _authorize(authorize);require_active_character(db,owner);require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        anvil_state=None
        if hammer is not None:
            from els_server.storage.anvil import snapshot as hammer_snapshot
            anvil_state=hammer_snapshot(db,owner,account_id)
        if old is not None:
            item=next((i for i in before if i['uid']==uid),None)
            response=[Event(0x201,kind=0x600,payload=acknowledgement(balance['ed'],uid,
                item.get('enhancement',0) if item else 0,changes=current_changes(db,operation,owner,0x5ff,old,before),anvil=anvil_state))]
            # Existing absolute sync may repair circuits using another writer.
            db.rollback();_authorize(authorize)
            if prepare_replay is not None:response=prepare_replay(response)
            for event in response:encode_event(event)
            _authorize(authorize)
            return response
        item=next((i for i in before if i['uid']==uid),None)
        if item is None:raise ValueError('Smith target is not owned')
        actor=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
        if actor is None or type(actor[0]) is not int or actor[0]<40:raise ValueError('Smith character level admission')
        from els_server.game_data import client_data
        if client_data().item(item['template'])['record'][0xd1]>actor[0]:raise ValueError('Smith target use level exceeds actor level')
        growth=snapshot(db,owner,account_id);state=ProfessionState(**growth['state']);q=quote(item,mode,state,hammer=hammer is not None)
        from els_server.domain.advanced_enhancement_materials import catalog
        used={};materials=[]
        requirements=[(STONES,1,4),((q['material'],),q['quantity'],3)]
        if mode in (1,2) and not q['ore_free']:
            requirements.append((catalog()['ore_templates' if mode==1 else 'crystal_templates'],1,4))
        if hammer=='el':requirements.append((catalog()['hammer_templates'],1,4))
        for templates,count,group in requirements:materials.extend(_allocate(before,templates,count,used,group))
        if hammer=='smith':
            from els_server.storage.anvil import spend_one
            anvil_state=spend_one(db,owner,account_id)

        next_state,xp,leveled=advance_blacksmith(state,q['xp'])
        ed=charge(db,owner,balance,q['ed'])
        result,updated=outcome(q,randbelow(q['denominator']))
        for material,amount in materials:
            if material['count']==amount:remove(db,owner,material)
            else:
                cursor=db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=? AND count>=?',(amount,owner,material['uid'],amount))
                if cursor.rowcount!=1:raise ValueError('Smith material changed')
        replace(db,owner,uid,q['level'],updated)
        from els_server.domain.enhancement_progress import after as progress_after
        from els_server.storage.enhancement_progress import replace as replace_progress
        gauge,points=progress_after(item,mode,result,updated)
        replace_progress(db,owner,dict(item,enhancement=updated),gauge,points)
        if xp:replace_profession(db,owner,account_id,growth['revision'],next_state)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({(m['group'],m['slot']) for m,amount in materials}|{(item['group'],item['slot'])})
        response=[Event(0x201,kind=0x600,payload=acknowledgement(ed,uid,updated,result,
            [(p,current.get(p)) for p in positions],profession_xp=xp,anvil=anvil_state))]
        if leveled:response.append(Event(0x201,kind=0x4c4,payload=level_update(owner,next_state,{})))
        for event in response:encode_event(event)
        _authorize(authorize)
        _commit(db,operation,digest,owner,0x5ff,positions,before,after)
        from els_server.storage.mentor45000_scope import paid
        response+=paid(db,owner,account_id,operation,q['level'],updated,result,lambda db:_authorize(authorize))
        _authorize(authorize)
        return response
