"""Consume one owned fixed cube and deliver its original contents atomically."""
from els_server.storage.item_actor import require_active_character
import secrets,sqlite3,struct
from contextlib import closing
from els_server.domain.cubes import catalog
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


def open_cube(path,owner,expected_template,payload,operation,randbelow=secrets.randbelow,*,account_id=None,prepare=None):
    from els_server.domain.job_reward_boxes import BOXES as job_boxes
    if expected_template in job_boxes:
        from els_server.storage.job_reward_boxes import open_box
        return open_box(path,owner,expected_template,payload,operation,account_id=account_id,prepare=prepare)
    if expected_template==715036:
        from els_server.storage.wardrobe_ticket_box import open_box
        return open_box(path,owner,payload,operation,account_id=account_id)
    from els_server.domain.published_2026_bundles import enabled
    definition=enabled().get(expected_template)
    if definition is not None:
        from els_server.storage.published_2026_bundles import open_bundle
        return open_bundle(path,owner,payload,operation,definition=definition)
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
        return open_box(path,owner,expected_template,payload,operation)
    from els_server.domain.boosting_2026_accessories import boxes as accessory_boxes
    if expected_template in accessory_boxes():
        from els_server.storage.boosting_2026_accessories import open_box
        return open_box(path,owner,expected_template,payload,operation)
    request=use_request(payload)
    if (any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3))
        or expected_template not in catalog()):raise ValueError('Unsupported fixed cube use')
    row=catalog()[expected_template]
    owned_reward=row.get('owned_reward_box',False)
    # Both fixed and selected cube quantity callbacks send Count here.
    # Zero is the original one-box route; one explicitly requests one box.
    # Bulk counts remain unsupported: never consume one for a larger request.
    if request.option not in (0,1):
        raise ValueError('Unsupported fixed cube quantity')
    from els_server.domain.regional_boss_cubes_legacy import BOXES,pool_for
    legacy=expected_template in BOXES
    growing=(expected_template==168889 and row.get('growing_adventure_kit')is True)
    if owned_reward:output=None
    elif row['selection_count']:
        if len(request.choices)!=1:raise ValueError('Select exactly one native cube item')
        output=next((e for e in row['entries'] if e['template']==request.choices[0]),None)
        if output is None:raise ValueError('Choice is outside this cube')
    else:
        if request.choices:raise ValueError('Fixed cube does not accept a choice')
        output=None if row.get('random')or growing else row['entries'][0]
    owner,digest=_identity(owner,0x196,struct.pack('>i',expected_template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        if legacy or owned_reward:_legacy_actor(db,owner,account_id,prepare)
        if growing:
            from els_server.domain.growing_adventure_kit import outputs_for
            role=db.execute('SELECT unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None:raise ValueError('Growing kit owner missing')
            kit_outputs=outputs_for(role[0])
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
            if legacy or owned_reward:
                from els_server.protocol.protocol_codec import encode_event
                for event in events:encode_event(event)
                _legacy_actor(db,owner,account_id,prepare)
            return events
        item=next((i for i in before if i['uid']==request.uid),None)
        if item is None or item['template']!=expected_template or item['group']!=4:
            raise ValueError('Fixed cube does not match owned previewed instance')
        require_current(item);require_unlocked(item)
        if balance['revision']>=2**63-1:raise ValueError('Fixed cube revision overflow')
        if legacy:
            role=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None:raise ValueError('Legacy cube owner missing')
            row=pool_for(row,*role)
        if row.get('random'):
            from els_server.domain.regional_boss_cubes import draw
            output=draw(row,randbelow(10000))
        owned_outputs=None
        if owned_reward:
            from els_server.storage.seal_quests import load_character
            from els_server.domain.owned_reward_boxes import selected_outputs,plan_for,DATA_SHA
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
        outputs=owned_outputs if owned_reward else kit_outputs if growing else(output,)
        plan=[]
        if not owned_reward:
            for selected in outputs:
                quantity=selected['quantity']
                while quantity:
                    delta=min(quantity,99);quantity-=delta
                    plan.append(dict(template=selected['template'],metadata=VERIFIED_TEMPLATES[selected['template']],
                        group=TEMPLATE_BAG_GROUPS[selected['template']],quantity=delta))
                    if growing:plan[-1]['enhancement']=selected['enhancement']
        reward_source=None
        if owned_reward:
            import time,uuid
            from els_server.domain.raid_reward_items import _issue_source
            epoch=int(time.time());plan=plan_for(expected_template,character,request.choices,epoch)
            identity=dict(policy='owned-reward-boxes-20261031-v1',definition_sha256=DATA_SHA,
                template=expected_template,owner=owner,uid=item['uid'],character=character,choices=list(request.choices),epoch=epoch)
            def authorize(db):
                _legacy_actor(db,owner,account_id,prepare)
                return True
            reward_source=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'owned-box:'+operation)),'box',identity,plan,authorize)
        grants=grant_items(db,plan,owner,regional_cube_source=regional_source,raid_reward_source=reward_source)
        if owned_reward:
            from els_server.domain.owned_reward_boxes import finalize_grants
            finalize_grants(db,owner,grants,outputs)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        positions=sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(selected['template'],selected['quantity'])for selected in outputs])
        if growing or legacy or owned_reward:
            from els_server.protocol.protocol_codec import encode_event
            for event in events:encode_event(event)
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        if legacy or owned_reward:_legacy_actor(db,owner,account_id,prepare)
        return events
