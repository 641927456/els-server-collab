"""Consume one owned fixed cube and deliver its original contents atomically."""
from els_server.storage.item_actor import require_active_character
import secrets,sqlite3,struct
from contextlib import closing
from els_server.domain.cubes import catalog,opening_count
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes


def _legacy_actor(db,owner,account_id,prepare):
    if not callable(prepare):raise ValueError('Legacy cube current selected actor callback required')
    prepare(db)
    require_active_character(db,owner)
    from els_server.storage.profession_state import require_owner
    require_owner(db,owner,account_id)


def _take_key(db,owner,items,key,quantity,positions):
    for item in items:
        if item['template']!=key or not item['count']:continue
        amount=min(quantity,item['count']);quantity-=amount
        positions.add((item['group'],item['slot']))
        if amount==item['count']:remove(db,owner,item)
        else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(amount,item['uid'],owner))
        item['count']-=amount
        if not quantity:return
    raise ValueError('Owned box key quantity changed')


def open_cube(path,owner,expected_template,payload,operation,randbelow=secrets.randbelow,*,account_id=None,prepare=None):
    from els_server.domain.modern_ice import boxes as ice_boxes
    if expected_template in ice_boxes():
        from els_server.storage.modern_ice import open_box
        return open_box(path,owner,expected_template,payload,operation,account_id=account_id,prepare=prepare)
    from els_server.domain.abyss_weapon_2026 import boxes as abyss_boxes
    if expected_template in abyss_boxes():
        from els_server.storage.abyss_weapon_boxes import open_box
        return open_box(path,owner,expected_template,payload,operation,account_id=account_id,prepare=prepare)
    from els_server.domain.job_reward_boxes import BOXES as job_boxes
    if expected_template in job_boxes:
        from els_server.storage.job_reward_boxes import open_box
        return open_box(path,owner,expected_template,payload,operation,account_id=account_id,prepare=prepare)
    from els_server.domain.growth_guide_boxes import boxes as guide_boxes
    if expected_template in guide_boxes():
        from els_server.storage.growth_guide_boxes import open_box
        return open_box(path,owner,expected_template,payload,operation)
    if expected_template==715036:
        from els_server.storage.wardrobe_ticket_box import open_box
        return open_box(path,owner,payload,operation,account_id=account_id)
    from els_server.domain.published_2026_bundles import enabled
    definition=enabled().get(expected_template)
    if definition is not None:
        from els_server.storage.published_2026_bundles import open_bundle
        return open_bundle(path,owner,payload,operation,definition=definition,account_id=account_id,prepare=prepare)
    from els_server.domain.boosting_2026_force_rewards import boxes as force_boxes
    if expected_template in force_boxes():
        from els_server.storage.boosting_2026_force_rewards import open_box
        return open_box(path,owner,expected_template,payload,operation)
    from els_server.domain.boosting_2026_participation_gear import BOX,enabled as gear_enabled
    if expected_template==BOX and gear_enabled():
        from els_server.storage.boosting_2026_participation_gear import open_gear
        return open_gear(path,owner,payload,operation,account_id=account_id,prepare=prepare)
    from els_server.domain.boosting_2026_fashion_rewards import BOXES,entries as fashion_entries
    if expected_template in BOXES and fashion_entries():
        from els_server.storage.boosting_2026_fashion_rewards import open_fashion
        return open_fashion(path,owner,expected_template,payload,operation)
    from els_server.domain.boosting_2026_nested_capacity import BOX as capacity_box,items as capacity_items
    if expected_template==capacity_box and capacity_items():
        from els_server.storage.boosting_2026_nested_capacity import open_box
        return open_box(path,owner,payload,operation)
    from els_server.domain.boosting_2026_title_rewards import BOX as title_box,enabled as title_enabled
    if expected_template==title_box and title_enabled():
        from els_server.storage.boosting_2026_title_rewards import open_box
        return open_box(path,owner,expected_template,payload,operation,account_id=account_id,prepare=prepare)
    from els_server.domain.boosting_2026_accessories import boxes as accessory_boxes
    if expected_template in accessory_boxes():
        from els_server.storage.boosting_2026_accessories import open_box
        return open_box(path,owner,expected_template,payload,operation)
    request=use_request(payload)
    if (any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3))
        or expected_template not in catalog()):raise ValueError('Unsupported fixed cube use')
    row=catalog()[expected_template]
    wedding=row.get('wedding_gift_box',False)
    owned_reward=row.get('owned_reward_box',False)or wedding
    from els_server.domain.regional_boss_cubes_legacy import BOXES,pool_for
    legacy=expected_template in BOXES
    guarded=legacy or owned_reward or row.get('retained_fixed_box',False) or row.get('pet_trainer_box',False) or row.get('relationship_box',False) or row.get('mentor_box',False) or row.get('guild_seed_pouch',False) or row.get('pet_expedition',False) or row.get('secret_fragment_box',False) or row.get('quick_start_box',False)
    growing=(expected_template==168889 and row.get('growing_adventure_kit')is True)
    if owned_reward:output=None
    elif row['selection_count']:
        if len(request.choices)!=1:raise ValueError('Select exactly one native cube item')
        output=next((e for e in row['entries'] if e['template']==request.choices[0]),None)
        if output is None:raise ValueError('Choice is outside this cube')
    else:
        if request.choices:raise ValueError('Fixed cube does not accept a choice')
        output=None if row.get('random')or row.get('resurrection_gain')or growing else row['entries'][0]
    owner,digest=_identity(owner,0x196,struct.pack('>i',expected_template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        if guarded:_legacy_actor(db,owner,account_id,prepare)
        if growing:
            from els_server.domain.growing_adventure_kit import outputs_for
            role=db.execute('SELECT unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None:raise ValueError('Growing kit owner missing')
            kit_outputs=outputs_for(role[0])
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))
            if row.get('resurrection_gain'):
                from els_server.protocol.known_resurrection import box_result
                from els_server.storage.resurrection_counter import count
                events+=box_result(balance['ed'],count(db,owner))
            else:events+=result(balance['ed'])
            if guarded:
                from els_server.protocol.protocol_codec import encode_event
                for event in events:encode_event(event)
                _legacy_actor(db,owner,account_id,prepare)
            return events
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=expected_template or item['group']!=row.get('group',4):
            raise ValueError('Fixed cube does not match owned previewed instance')
        require_current(item);require_unlocked(item)
        openings=opening_count(request.option,item['count'])
        opening_ed=row.get('opening_ed',0)*openings
        if opening_ed>balance['ed']:raise ValueError('Cube opening ED insufficient')
        remaining_ed=balance['ed']-opening_ed
        if row.get('retained_fixed_box'):
            import time
            retained_epoch=int(time.time())
            from els_server.domain.retained_box_openings import require_usable
            from els_server.storage.seal_quests import load_character
            retained_character=load_character(db,owner,account_id,identity_only=True)
            if row.get('retained_role_box'):
                from els_server.storage.luciel_state import active_state
                retained_character['active_unit']=active_state(db,owner)['active_unit']if retained_character['unit_type']==10 else 0
                if row.get('retained_active_side')and request.flag2!=retained_character['active_unit']:raise ValueError('Retained box active side mismatch')
            require_usable(expected_template,retained_character,item)
            if row.get('retained_local_box'):
                from els_server.domain.retained_box_openings import branches_for
                from els_server.domain.item_expiration import expired
                from els_server.domain.item_locks import locked
                retained_branches={b['key']:b for b in branches_for(expected_template,retained_character)}
                key_items=[dict(i)for i in before if i['template']in retained_branches and not expired(i,now=retained_epoch)and not locked(i,now=retained_epoch)and not i.get('sealed',False)]
                key_items.sort(key=lambda i:(i['template'],i['group'],i['slot'],i['uid']))
        if row.get('mentor_box')and(item.get('sealed',False)or item.get('seal_used',0)):
            raise ValueError('Mentor box seal state')
        if balance['revision']>=2**63-1:raise ValueError('Fixed cube revision overflow')
        if legacy:
            role=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None:raise ValueError('Legacy cube owner missing')
            row=pool_for(row,*role)
        batch_grants=[];batch_outputs=[];key_positions=set()
        for opening in range(openings):
            unit_operation=operation if opening==0 else operation+':'+str(opening)
            if row.get('retained_local_box'):
                from els_server.domain.retained_box_openings import draw_outputs
                key=next((k for k,b in sorted(retained_branches.items())if k==0 or sum(i['count']for i in key_items if i['template']==k)>=b['key_count']),None)
                if key is None:raise ValueError('Owned box opening key required')
                retained_branch=retained_branches[key]
                retained_outputs,retained_roll=draw_outputs(retained_branch,randbelow)
                if key:_take_key(db,owner,key_items,key,retained_branch['key_count'],key_positions)
            if row.get('random'):
                from els_server.domain.regional_boss_cubes import draw
                output=draw(row,randbelow(row.get('draw_total',10000)))
            owned_outputs=None
            if owned_reward:
                from els_server.storage.seal_quests import load_character
                if wedding:
                    from els_server.domain.wedding_gifts import selected_outputs,plan_for,definition_sha
                    from els_server.storage.luciel_state import active_state
                    character=load_character(db,owner,account_id,identity_only=True)
                    character['active_unit']=active_state(db,owner)['active_unit']if character['unit_type']==10 else 0
                    if request.flag2!=character['active_unit']:raise ValueError('Wedding gift active side mismatch')
                else:
                    from els_server.domain.owned_reward_boxes import selected_outputs,plan_for,definition_sha
                    character=load_character(db,owner,account_id)
                owned_outputs=selected_outputs(expected_template,character,request.choices)
                if item.get('sealed',False):raise ValueError('Unseal owned reward box before opening')
            regional_source=None
            if legacy:
                from els_server.storage.regional_boss_cube_source import _OwnedCubeSource
                regional_source=_OwnedCubeSource(db,owner,item,output)
            source=(item['group'],item['slot'])
            if item['count']==1:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
            if regional_source is not None:regional_source.debit_complete()
            outputs=owned_outputs if owned_reward else kit_outputs if growing else tuple(row['entries']) if row.get('quick_start_box')or row.get('retained_fixed_box') else(output,)
            if row.get('retained_role_box'):
                from els_server.domain.retained_box_openings import outputs_for
                outputs=retained_outputs if row.get('retained_local_box')else outputs_for(expected_template,retained_character)
            if row.get('resurrection_gain'):outputs=()
            plan=[]
            if not owned_reward and not row.get('retained_fixed_box'):
                for selected in outputs:
                    quantity=selected['quantity']
                    while quantity:
                        delta=min(quantity,99);quantity-=delta
                        plan.append(dict(template=selected['template'],metadata=VERIFIED_TEMPLATES[selected['template']],
                            group=TEMPLATE_BAG_GROUPS[selected['template']],quantity=delta))
                        if growing:plan[-1]['enhancement']=selected['enhancement']
            reward_source=None
            if row.get('relationship_box') and row.get('random'):
                import uuid
                from els_server.domain.raid_reward_items import _issue_source
                from els_server.domain.relationship_boxes import POLICY,DATA_SHA
                identity=dict(policy=POLICY,definition_sha256=DATA_SHA,box=expected_template,
                              owner=owner,uid=item['uid'],output=output)
                def anniversary_guard(db):
                    _legacy_actor(db,owner,account_id,prepare)
                    return True
                reward_source=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'anniversary-box:'+unit_operation)),
                    'box',identity,plan,anniversary_guard)
            if owned_reward:
                import time,uuid
                from els_server.domain.raid_reward_items import _issue_source
                epoch=int(time.time());plan=plan_for(expected_template,character,request.choices,epoch)
                identity=dict(policy='wedding-gifts-first-use-20261106-v1'if wedding else'owned-reward-boxes-20261031-v1',definition_sha256=definition_sha(expected_template),
                    template=expected_template,owner=owner,uid=item['uid'],character=character,choices=list(request.choices),epoch=epoch)
                def authorize(db):
                    _legacy_actor(db,owner,account_id,prepare)
                    if wedding:
                        current=load_character(db,owner,account_id,identity_only=True)
                        current['active_unit']=active_state(db,owner)['active_unit']if current['unit_type']==10 else 0
                        if current!=character:raise ValueError('Wedding gift actor changed')
                    return True
                reward_source=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'owned-box:'+unit_operation)),'box',identity,plan,authorize)
            if row.get('secret_fragment_box'):
                # Same exact owned-box debit and factory authority used by current
                # reward boxes; this does not globally reopen compatibility gear.
                import uuid
                from els_server.domain.raid_reward_items import _issue_source
                identity=dict(policy=row['policy'],template=expected_template,owner=owner,
                    uid=item['uid'],output=output,box_debit=1)
                def secret_guard(db):
                    _legacy_actor(db,owner,account_id,prepare)
                    return True
                reward_source=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'secret-fragment-box:'+unit_operation)),
                    'box',identity,plan,secret_guard)
            if row.get('retained_fixed_box')and not row.get('resurrection_gain'):
                import uuid
                from els_server.domain.retained_box_openings import plan_for,plan_from_outputs,POLICY,definition_sha
                from els_server.domain.raid_reward_items import _issue_source
                plan=plan_from_outputs(outputs,retained_epoch)if row.get('retained_local_box')else plan_for(expected_template,retained_epoch,retained_character)
                identity=dict(policy=POLICY,definition_sha256=definition_sha(expected_template),template=expected_template,
                    uid=item['uid'],owner=owner,box_debit=1,epoch=retained_epoch)
                if row.get('retained_role_box'):identity['character']=retained_character
                if row.get('retained_local_box'):identity.update(key=key,key_debit=retained_branch['key_count'],roll=retained_roll)
                def retained_guard(db):
                    _legacy_actor(db,owner,account_id,prepare)
                    if row.get('retained_role_box'):
                        current=load_character(db,owner,account_id,identity_only=True)
                        current['active_unit']=active_state(db,owner)['active_unit']if current['unit_type']==10 else 0
                        if current!=retained_character:raise ValueError('Retained box actor changed')
                    return True
                reward_source=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'retained-fixed-box:'+unit_operation)),
                    'box',identity,plan,retained_guard)
            grants=[]if row.get('resurrection_gain')else grant_items(db,plan,owner,regional_cube_source=regional_source,raid_reward_source=reward_source)
            if owned_reward and not wedding:
                from els_server.domain.owned_reward_boxes import finalize_grants
                finalize_grants(db,owner,grants,outputs)
            batch_grants.extend(grants);batch_outputs.extend(outputs)
            source_grant=next((g for g in grants if g['uid']==item['uid']),None)
            item=dict(item,count=source_grant['count']if source_grant is not None else item['count']-1)
        grants=batch_grants;outputs=batch_outputs
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*key_positions,*[(i['group'],i['slot']) for i in grants]})
        events=result(remaining_ed,[(p,current.get(p)) for p in positions],[(selected['template'],selected['quantity'])for selected in outputs])
        if row.get('resurrection_gain'):
            from els_server.storage.resurrection_counter import count,MAX_COUNT
            from els_server.storage.known_resurrection import _set
            from els_server.protocol.known_resurrection import box_result
            value=count(db,owner)+row['resurrection_gain']*openings
            if value>MAX_COUNT:raise ValueError('Mentor resurrection credit overflow')
            _set(db,owner,value)
            events=box_result(remaining_ed,value,[(p,current.get(p))for p in positions])
        from els_server.protocol.protocol_codec import encode_event
        for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=?',(remaining_ed,owner))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        if guarded:_legacy_actor(db,owner,account_id,prepare)
        return events
