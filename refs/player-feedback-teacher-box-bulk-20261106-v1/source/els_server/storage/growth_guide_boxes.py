"""Owned guide boxes use the common inventory receipt and atomic factory."""
from contextlib import closing
import sqlite3,struct,time
from els_server.domain.growth_guide_boxes import boxes,outputs_for,plans_for,validate_grants
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.item_actor import require_active_character
from els_server.storage.npc_trade import balances

def open_box(path,owner,template,payload,operation,*,now=None):
    req=use_request(payload)
    if req.option<0 or any(v not in (0,1) for v in (req.flag1,req.flag2,req.flag3)):raise ValueError('Guide box native mode')
    owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        now=int(time.time()) if now is None else now
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
            for event in events:encode_event(event)
            return events
        item=next((i for i in before if i['uid']==req.uid),None)
        if item is None or item['template']!=template or item['group']!=4:raise ValueError('Guide owned previewed box required')
        require_current(item,now=now);require_unlocked(item,now=now)
        count=req.option or 1
        if count>item['count']:raise ValueError('Guide box quantity exceeds owned stack')
        from els_server.storage.seal_quests import load_character
        character=load_character(db,owner)
        # Lu/Ciel active side is part of the saved role, never a choice UID.
        from els_server.storage.luciel_state import active_state
        character['luciel_active_unit']=active_state(db,owner)['active_unit']
        rows=outputs_for(template,character)
        if boxes()[template]['selection_count']:rows=tuple(r for r in rows if r['template'] in req.choices)
        plans=plans_for(rows,now,count);context=(template,character,req.choices,now,count)
        validate_grants(context,plans)
        if balance['revision']>=2**63-1:raise ValueError('Guide box inventory revision overflow')
        source=(item['group'],item['slot'])
        if item['count']==count:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(count,item['uid'],owner))
        grants=grant_items(db,plans,owner,growth_guide_box=context)
        from els_server.storage.equipment_options import replace as options
        from els_server.storage.equipment_reforge import replace as reforge
        from els_server.storage.equipment_identification import replace as identify
        for item in grants:
            r=next(r for r in rows if r['template']==item['template'])
            if r.get('reforge_level'):reforge(db,owner,item['uid'],[0,100,0],[r['reforge_level'],100,0])
            if r.get('option_groups'):
                options(db,owner,item['uid'],item.get('option_groups',{}),{**item.get('option_groups',{}),**r['option_groups']})
                if item.get('identified') is False:identify(db,owner,item['uid'],False,True)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r['template'],r['quantity']*count) for r in rows])
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        require_active_character(db,owner)
        return events
