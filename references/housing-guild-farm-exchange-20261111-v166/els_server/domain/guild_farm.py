"""Current native farm, current GuildData crops, original inventory and mail."""
import struct
from els_server.domain import guild_rules as rules
from els_server.storage import guild_system_state as system
from els_server.protocol import guild_farm_messages as wire
from els_server.protocol.social_messages import Reader
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.storage.inventory_actions import _commit,_previous

KINDS=frozenset((0x7fa,0x7fd,0x7ff,0x801,0x803,0x805,0x807,0x822))
READS=frozenset((0x7fa,0x807,0x822))

def empty():return dict(plant=0,planted=0,matures=0,fertilized=False,watered=0,waterer=0)

def water(state,owner,now):
    value=state['watering'].get(str(owner),dict(count=state['farm_slots'],refilled=now))
    ticks=max(0,(now-value['refilled'])//3600)
    return dict(count=min(state['farm_slots'],value['count']+ticks),refilled=value['refilled']+ticks*3600)

def rows(db,saved,now):
    state=saved['system'];result=[]
    for owner,name,class_id in db.execute('SELECT m.owner,c.name,c.unit_class FROM native_guild_members m JOIN characters c ON c.uid=m.owner WHERE m.guild_id=? ORDER BY m.owner',(saved['id'],)):
        value=water(state,owner,now);plots=state['plots'].get(str(owner),{})
        result.append(dict(owner=owner,name=name,class_id=class_id,water=value['count'],refill=value['refilled']+3600,
            plots={slot:plots.get(str(slot),empty())for slot in range(1,state['farm_slots']+1)}))
    return result

def _slot(state,owner,slot):
    if not 1<=slot<=state['farm_slots']:raise ValueError('Unowned farm plot')
    return state['plots'].setdefault(str(owner),{}).setdefault(str(slot),empty())

def replay(db,saved,kind,payload,operation,digest,now):
    if kind==0x807:return [wire.reply(0x808,struct.pack('>ii',0,saved['system']['fertilizer']))]
    if kind in READS:return [wire.overview(rows(db,saved,now),saved['system']['fertilizer'])if kind==0x7fa else wire.updated(rows(db,saved,now),0x823)]
    r=Reader(payload)
    if kind==0x801:return [wire.updated(rows(db,saved,now),0x802)]
    slot=r.scalar('i');value=_slot(saved['system'],saved['owner'],slot)
    changes=()
    if kind in(0x7fd,0x803):
        positions=_previous(db,operation,digest)
        if positions is None:raise ValueError('Farm receipt lost inventory producer')
        from els_server.storage.equipment_receipt_state import current_changes
        changes=current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner']))
    return [wire.changed(kind+1,saved['owner'],slot,value,changes)]

def command(db,s,event,saved,operation,now):
    state=saved['system'];owner=saved['owner'];kind=event.kind;r=Reader(event.payload);earned=0
    if kind==0x807:
        r.end();return [wire.reply(0x808,struct.pack('>ii',0,state['fertilizer']))],[]
    if kind in READS:
        r.end();return [wire.overview(rows(db,saved,now),state['fertilizer'])if kind==0x7fa else wire.updated(rows(db,saved,now),0x823)],[]
    if s.phase!='guild_agit_ready':raise ValueError('Guild farming requires actual GuildAgit ready')
    if kind==0x801:
        target=r.scalar('Q');slot=r.scalar('i');r.end()
        if target==owner or target not in saved['members']:raise ValueError('Water another actual guild member')
        value=_slot(state,target,slot);supply=water(state,owner,now)
        if not value['plant']or value['watered']or supply['count']<1:raise ValueError('Farm water availability')
        value.update(watered=now,waterer=owner);supply['count']-=1;state['watering'][str(owner)]=supply
        earned=system.honor(state,owner,dict(rules.calls('SetGuildHonorPoint'))[3],now)
        answer=[wire.updated(rows(db,saved,now),0x802)]
    else:
        slot=r.scalar('i');value=_slot(state,owner,slot);before=load_items(db,owner);positions=[]
        if kind==0x7fd:
            seed=r.scalar('Q');r.end()
            if value['plant']:raise ValueError('Farm plot is planted')
            item=next((i for i in before if i['uid']==seed),None)
            plant=next((p for p in rules.plants().values()if item and p['SEED_ITEM_ID']==item['template']),None)
            if plant is None:raise ValueError('Owned current guild seed required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            require_current(item,now=now);require_unlocked(item,now=now)
            if item['count']==1:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,seed))
            positions=[(item['group'],item['slot'])]
            value.update(plant=plant['GUILD_PLANT_ID'],planted=now,matures=now+plant['TIME'],fertilized=False,watered=0,waterer=0)
        elif kind==0x7ff:
            r.end()
            if not value['plant']:raise ValueError('Farm plot is empty')
            value.clear();value.update(empty())
        elif kind==0x805:
            r.end()
            if not value['plant']or value['fertilized']or state['fertilizer']<1:raise ValueError('Farm fertilizer availability')
            value['fertilized']=True;state['fertilizer']-=1
        elif kind==0x803:
            r.end()
            if not value['plant']or value['matures']>now:raise ValueError('Farm crop has not matured')
            plant=rules.plants()[value['plant']];base=plant['DEFAULT_RESULT_AMOUNT']
            quantity=min(plant['MAX_RESULT_AMOUNT'],base*(100+30*value['fertilized']+20*bool(value['watered']))//100)
            from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
            template=plant['RESULT_ITEM_ID']
            granted=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],owner)
            positions=[(i['group'],i['slot'])for i in granted]
            if value['waterer']:
                from els_server.storage.guild_reward_mail import farm_share
                farm_share(db,saved,owner,value,plant,operation,now)
            value.clear();value.update(empty())
            earned=system.honor(state,owner,dict(rules.calls('SetGuildHonorPoint'))[2],now)
        else:raise ValueError('Farm request is not registered')
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        changes=[(p,current.get(p))for p in sorted(set(positions))]
        if kind in(0x7fd,0x803):
            import hashlib
            digest=hashlib.sha256(str(owner).encode()+b':'+str(kind).encode()+b':'+event.payload).hexdigest()
            _commit(db,operation,digest,owner,kind,positions,before,after)
        answer=[wire.changed(kind+1,owner,slot,value,changes)]
    system.write(db,saved['id'],state)
    from els_server.storage.guild_quests import record as quest_record
    activity={0x7fd:65,0x805:66,0x801:67,0x803:68}.get(kind)
    answer+=quest_record(db,owner,operation,([(activity,1,0)]if activity else [])+([(100,earned,0)]if earned else []),now)
    return answer,[wire.updated(rows(db,saved,now))]

def failure(kind):
    if kind==0x807:return wire.reply(0x808,struct.pack('>ii',1,0))
    if kind==0x7fa:return wire.overview((),0,1)
    if kind in(0x801,0x822):return wire.reply(kind+1,struct.pack('>iI',1,0))
    return wire.changed(kind+1,0,0,empty(),code=1)
