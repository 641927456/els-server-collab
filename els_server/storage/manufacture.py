"""Atomic, owner-scoped compatibility crafting. See manufacture_policy.json."""
import hashlib,json,secrets,sqlite3,struct
from collections import Counter
from contextlib import closing
from pathlib import Path
from dataclasses import asdict
from els_server.manufacture_data import manufacture_data
from els_server.game_data import client_data
from els_server.protocol.manufacture_messages import manufacture_request,manufacture_ack
from els_server.protocol.profession_messages import ProfessionState,selection_ack
from els_server.domain.manufacture_rules import policy,inventory_definitions,output_quantity,xp_advance,socket_capacity
from els_server.domain.manufacture_requirements import requirements,inventory_candidates,inspect_profession
from els_server.storage.profession_state import snapshot,replace
from els_server.storage.inventory_state import load_items,grant_items,InventoryFull
from els_server.storage.item_instances import insert,next_uid
from els_server.storage.reward_state import validate_balances
from els_server.storage.bag_capacity import allowances
from els_server.storage.manufacture_debits import apply_debits
from els_server.storage.manufacture_quota import RECIPE as LIMITED,ensure_schema,reserve
from els_server.storage.manufacture_receipt_state import replay_refresh

def operation_identity(operation):
    if type(operation) is not str or not 1<=len(operation)<=160:raise ValueError('Invalid manufacture operation ID')

def double_title_equipped(db,owner,now):
    # 1240 / socket 74064 is the currently equipped Ultimate Truth title.
    # Use committed canonical ownership, scope, eligibility and expiry in this
    # crafting transaction. Its other socket effect remains client-owned.
    from els_server.storage.titles import exists,snapshot as title_snapshot
    if exists(db,'title_ownership') or exists(db,'title_equipment'):
        return title_snapshot(db,owner,now)['title']==1240
    # Preserve the explicitly configured pre-title-system compatibility bridge
    # only for old saves without canonical title state. Never override unequip
    # or expiration with a stale bridge once canonical title state exists.
    if exists(db,'manufacture_entitlements'):
        row=db.execute('SELECT double_title FROM manufacture_entitlements WHERE owner=?',(owner,)).fetchone()
        return bool(row and row[0]==1)
    return False

def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS manufacture_receipts (
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,
        request_hash TEXT NOT NULL,positions_json TEXT NOT NULL,audit_json TEXT NOT NULL)''')

def available_recipe(recipe,town):
    # A request carries no NPC identity. Enforce the server-owned town and the
    # known NPC-to-town mapping; table-only legacy recipes use explicit fallback.
    from els_server.storage.local_state import TOWN_SCENES
    if town not in TOWN_SCENES:raise ValueError('Crafting requires a supported town')
    rows=recipe['village_registrations']
    if rows:
        from els_server.domain.npc_trade import stock
        # SERVER_GROUP_ID is a realm identifier (e.g. Ventus=2), not a
        # country code. Compatibility realm intentionally admits all groups.
        npcs={row[1] for row in rows}
        towns={t for t,npc in stock() if npc in npcs}
        if towns and town not in towns:raise ValueError('Recipe belongs to another town')

def allocate(request,items,demand,now):
    candidates=inventory_candidates(items,now=now)
    usable={uid:t for t,rows in candidates.items() for uid,count in rows}
    explicit=(() if request.selected_uid==-1 else (request.selected_uid,))+request.auxiliary_uids
    for uid in explicit:
        if uid not in usable or usable[uid] not in demand:raise ValueError('Invalid explicit crafting instance')
    rank={uid:i for i,uid in enumerate(explicit)};result=[]
    for template,need in demand.items():
        for uid,count in sorted(candidates.get(template,()),key=lambda p:(rank.get(p[0],len(rank)),p[0])):
            take=min(count,need)
            if take:result.append(dict(uid=uid,quantity=take));need-=take
            if not need:break
        if need:raise ValueError('Insufficient crafting materials')
    return tuple(result)

def candidates_for(recipe,character,source):
    from els_server.domain.acquisition_policy import can_acquire
    from els_server.domain.equipment_requirements import class_matches
    registered=inventory_definitions();result=[]
    for t in sorted(set(recipe['result_registrations'])):
        if t not in registered or not can_acquire(t):continue
        d=client_data().item(t);raw=d['record']
        if d['item_type'] in (1,2) and (raw[210] and raw[210]!=character[0] or raw[211] and not class_matches(character[1],raw[211])):continue
        result.append(t)
    if source and len(result)>1:
        alternate=[t for t in result if t!=source['template']]
        if alternate:result=alternate
    if not result:raise ValueError('No available crafting outcome')
    return result

def make_item(db,owner,template,items,source=None,*,randbelow=secrets.randbelow):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item
    d=client_data().item(template);group=TEMPLATE_BAG_GROUPS[template]
    if source:
        uid=source['uid']
        slot=source['slot'] if source['group']==group else None
    else:uid=next_uid(db);slot=None
    if slot is None:
        occupied={x['slot'] for x in items if x['group']==group}
        slot=next((n for n in range(allowances(db,owner)[group]) if n not in occupied),None)
    if slot is None:raise InventoryFull('Crafting output bag is full')
    out=dict(uid=uid,template=template,metadata=VERIFIED_TEMPLATES[template],count=1,group=group,slot=slot)
    if d['item_type'] in (1,2):
        from els_server.domain.normal_equipment import definitions
        normal=template in definitions()
        if normal:
            maximum=struct.unpack_from('<h',d['record'],0xc8)[0]
            if maximum>0:out['durability']=maximum
        # Documented old random effects reset. Compatibility reset means
        # unidentified; explicit identify action uses the configured fallback.
        if normal:out['identified']=False
        if source:
            if 'enhancement' in source:out['enhancement']=source['enhancement']
            # Preserve equipment-v2+ per-instance protection state on same-UID upgrade.
            for key in ('enhancement_gauge','enhancement_guarantee'):
                if key in source:out[key]=source[key]
            if 'attributes' in source:out['attributes']=list(source['attributes'])
            sockets=list(source.get('option_groups',{}).get('0',[]))
            capacity=socket_capacity(template)
            if len(sockets)>capacity:raise ValueError('Upgrade would lose expanded sockets')
            if sockets:out['option_groups']={'0':sockets+[0]*(capacity-len(sockets))}
    from els_server.domain.equipment_circuit_rules import material as circuit_material,target as circuit_target,generate as circuit_generate,validate_material as circuit_values,validate_grid as circuit_grid
    if source and '28' in source.get('option_groups',{}):
        old_target=circuit_target(source['template']);new_target=circuit_target(template)
        if old_target is None or new_target is None or old_target['part']!=new_target['part']:raise ValueError('Upgrade would lose circuit armor state')
        out.setdefault('option_groups',{})['28']=circuit_grid(template,source['option_groups']['28'])
    if circuit_material(template) is not None:
        prior=source.get('option_groups',{}).get('1') if source else None
        generated={'1':circuit_values(template,prior)} if prior is not None else circuit_generate(template,randbelow)
        out.setdefault('option_groups',{}).update(generated)
    from els_server.domain.equipment_chip_rules import material as chip_material,target as chip_target,generate as chip_generate,source_options as chip_source,armor_options as chip_armor,state as chip_state
    if source and (chip_material(source['template']) or 'chip_tuning' in source):
        if not chip_material(template):raise ValueError('Upgrade would lose chip tuning')
        out.setdefault('option_groups',{})['1']=chip_source(source.get('option_groups',{}).get('1',[]))
        if 'chip_tuning' in source:out['chip_tuning']=chip_state(template,source['chip_tuning'])
    elif chip_material(template):out.setdefault('option_groups',{}).update(chip_generate(randbelow))
    if source and '27' in source.get('option_groups',{}):
        old_target=chip_target(source['template']);new_target=chip_target(template)
        if old_target is None or new_target is None or old_target['part']!=new_target['part']:raise ValueError('Upgrade would lose installed chip')
        out.setdefault('option_groups',{})['27']=chip_armor(template,source['option_groups']['27'])
    if source and ('reforge' in source or '13' in source.get('option_groups',{})):
        from els_server.domain.equipment_reforge_rules import target as reforge_target,state as reforge_state,validate_instance as validate_reforge
        validate_reforge(source)
        old_reforge=reforge_target(source['template']);new_reforge=reforge_target(template)
        if old_reforge is None or new_reforge is None or (old_reforge['reforge_class'],old_reforge['part'])!=(new_reforge['reforge_class'],new_reforge['part']):raise ValueError('Upgrade would lose reforge state or milestones')
        if 'reforge' in source:out['reforge']=reforge_state(template,source['reforge'])
        out.setdefault('option_groups',{})['13']=list(source['option_groups']['13'])
    if source and any(g in source.get('option_groups',{}) for g in ('14','15','16')):
        from els_server.domain.equipment_engrave_rules import target as engrave_target,options as engrave_options
        if engrave_target(source['template']) is None or engrave_target(template) is None:raise ValueError('Upgrade would lose installed engraving')
        for group in ('14','15','16'):
            if group in source['option_groups']:out.setdefault('option_groups',{})[group]=engrave_options(template,int(group),source['option_groups'][group])
    if source:
        out.update(sealed=False,seal_used=source.get('seal_used',0))
        if 'expires_at' in source:out['expires_at']=source['expires_at']
    return validate_item(out)

def execute(path,owner,account_id,payload,operation,*,now,randbelow=secrets.randbelow):
    operation_identity(operation);request=manufacture_request(payload);p=policy()
    if type(now) is not int or now<0 or request.quantity>p['max_batch']:raise ValueError('Craft request bound')
    digest=hashlib.sha256(payload).hexdigest();recipe=manufacture_data().recipe(request.recipe_id)
    definition=recipe['definition'];upgrade=bool(definition.get('m_bUpgrade'))
    if upgrade and request.quantity!=1:raise ValueError('Upgrade requires one selected instance')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            current=_active_owner(db,owner,account_id);state=ProfessionState(**current['state'])
            items=load_items(db,owner);balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
            ensure(db);old=db.execute('SELECT owner,account_id,request_hash,positions_json,audit_json FROM manufacture_receipts WHERE operation=?',(operation,)).fetchone()
            if old:
                if old[:3]!=(owner,account_id,digest):raise ValueError('Conflicting manufacture retry')
                positions=json.loads(old[3]);by_pos={(i['group'],i['slot']):i for i in items}
                refresh,legacy=replay_refresh(positions,old[4],items)
                response=manufacture_ack(result=0,rewards={},changes=[(tuple(pos),by_pos.get(tuple(pos))) for pos in positions],ed=balances['ed'],profession_xp=0,limit_id=0,limit_value=0)
                db.rollback();return dict(response=response,replayed=True,requires_inventory_sync=True,leveled=False,state=state,inventory=items,inventory_refresh=refresh,legacy_receipt_inventory_refresh=legacy)
            character=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
            town=db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()
            if character is None or town is None:raise ValueError('Crafting owner location missing')
            available_recipe(recipe,town[0])
            if not inspect_profession(request.recipe_id,state)['fits']:raise ValueError('Craft profession requirement')
            demand=requirements(request.recipe_id,request.quantity)
            allocation=allocate(request,items,demand['materials'],now)
            # Preserve installed original mystic sockets until crafting migration is qualified.
            consumed_uids={a['uid'] for a in allocation}
            if any(i['uid'] in consumed_uids and any(any(i.get('option_groups',{}).get(g,[])) for g in ('9','10','11','12')) for i in items):raise ValueError('Mystic socket crafting migration is not qualified')
            source=None
            if upgrade:
                eligible=[i for i in items if any(a['uid']==i['uid'] and a['quantity']==1 for a in allocation)
                          and i['count']==1 and client_data().item(i['template'])['item_type'] in (1,2,3)]
                source=next((i for i in eligible if i['uid']==request.selected_uid),None) if request.selected_uid!=-1 else next(iter(eligible),None)
                if source is None and any(client_data().item(t)['item_type'] in (1,2,3) for t in demand['materials']):raise ValueError('Upgrade source not selected/consumed')
            selected=next((i for i in items if i['uid']==request.selected_uid),None)
            pool=candidates_for(recipe,character,source or selected)
            if balances['ed']<demand['base_ed'] or balances['revision']>=2**63-1:raise ValueError('Craft ED insufficient/bound')
            quota=None
            if request.recipe_id==LIMITED:
                ensure_schema(db);quota=reserve(db,owner,account_id,request.recipe_id,request.quantity,now=now,region='CN')
            double=double_title_equipped(db,owner,now)
            rewards=Counter()
            for _ in range(request.quantity):
                index=randbelow(len(pool)) if len(pool)>1 else 0
                if type(index) is not int or not 0<=index<len(pool):raise ValueError('Craft RNG range')
                n=output_quantity(request.recipe_id)
                if double and definition.get('m_RequireProfessionType')==3 and quota is None and not upgrade:
                    roll=randbelow(100)
                    if type(roll) is not int or not 0<=roll<100:raise ValueError('Craft title RNG range')
                    if roll<p['title_double_percent']:n*=2
                rewards[pool[index]]+=n
            if upgrade and (len(rewards)!=1 or sum(rewards.values())!=1):raise ValueError('Upgrade must create one instance')
            next_state,xp,leveled=xp_advance(state,definition.get('m_LimitProfessionLevel',0),request.quantity)
            apply_debits(db,owner,account_id,demand['materials'],allocation,now=now)
            for template,n in sorted(rewards.items()):
                d=client_data().item(template)
                if source is not None or d['item_type'] in (1,2,3):
                    for _ in range(n):
                        out=make_item(db,owner,template,load_items(db,owner),source,randbelow=randbelow)
                        insert(db,owner,out)
                else:
                    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
                    remaining=n
                    while remaining:
                        take=min(remaining,99)
                        grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=take)],owner)
                        remaining-=take
            replace(db,owner,account_id,current['revision'],next_state)
            ed=balances['ed']-demand['base_ed']
            if db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=? AND revision=?',(ed,owner,balances['revision'])).rowcount!=1:raise ValueError('Stale crafting ED')
            after=load_items(db,owner);before_slots={(i['group'],i['slot']):i for i in items};after_slots={(i['group'],i['slot']):i for i in after}
            positions=[pos for pos in sorted(before_slots.keys()|after_slots.keys()) if before_slots.get(pos)!=after_slots.get(pos)]
            response=manufacture_ack(result=0,rewards=dict(rewards),changes=[(pos,after_slots.get(pos)) for pos in positions],ed=ed,profession_xp=xp,
                                     limit_id=request.recipe_id if quota else 0,limit_value=quota['used'] if quota else 0)
            audit=dict(policy='compatibility-v1',recipe=request.recipe_id,quantity=request.quantity,allocation=allocation,
                       rewards=dict(rewards),cost=demand['base_ed'],xp=xp,profession=asdict(next_state),
                       affected_uids=sorted({i['uid'] for i in items+after if (i['group'],i['slot']) in set(positions)}))
            db.execute('INSERT INTO manufacture_receipts VALUES(?,?,?,?,?,?)',(operation,owner,account_id,digest,json.dumps(positions),json.dumps(audit,sort_keys=True)))
            db.commit();return dict(response=response,replayed=False,requires_inventory_sync=False,leveled=leveled,state=next_state,inventory=after,audit=audit)
        except BaseException:db.rollback();raise

def select_alchemist(path,owner,account_id,payload):
    from els_server.protocol.profession_messages import select_request
    if select_request(payload)!=3:raise ValueError('This route implements alchemist crafting only')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE');old=_active_owner(db,owner,account_id)
            character=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
            if character[0]<40 or old['state']['profession'] not in (0,3):raise ValueError('Alchemist selection unavailable')
            state=ProfessionState(**old['state'])
            if state.profession==0:state=ProfessionState(3,1,0,{},0,policy()['level_thresholds']['1'])
            replace(db,owner,account_id,old['revision'],state)
            wire=selection_ack(0,state,{},tail_u64=0,tail_i32=0,tail_flag_a=False,tail_flag_b=False)
            db.commit();return wire
        except BaseException:db.rollback();raise


def _active_owner(db,owner,account_id):
    """Keep lifecycle and ownership current inside the mutation transaction."""
    from els_server.storage.character_lifecycle import states
    current=snapshot(db,owner,account_id)
    lifecycle=states(db,(owner,)).get(owner,{})
    if lifecycle.get('requested_at') or lifecycle.get('finalized_at'):
        raise ValueError('Crafting character is pending deletion or finalized')
    return current
