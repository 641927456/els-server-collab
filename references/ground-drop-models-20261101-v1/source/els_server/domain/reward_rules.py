"""Explicit local reward policy cross-checked against native definitions."""
from els_server.domain.ground_currency import coin_template
import functools
import hashlib
import uuid
import json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data


@functools.lru_cache(maxsize=1)
def _policy():
    policy=json.loads((PROJECT_ROOT/'config/reward_rules.json').read_text(encoding='utf8'))
    if policy['schema_version']!=1 or policy['provenance']!='local_policy':raise ValueError('Reward policy provenance')
    return policy


def item_plan(template, quantity):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    native=client_data().item(template)
    if template not in VERIFIED_TEMPLATES or native['metadata']!=VERIFIED_TEMPLATES[template]:
        raise ValueError('Reward item wire format is not verified')
    if type(quantity) is not int or not 1<=quantity<=999:raise ValueError('Reward quantity bound')
    return dict(template=template,quantity=quantity,metadata=native['metadata'],group=TEMPLATE_BAG_GROUPS[template])


def dungeon_rewards(dungeon_id):
    client_data().dungeon(dungeon_id)
    rule=_policy()['dungeons'].get(str(dungeon_id))
    if rule is None:raise ValueError('No verified reward policy for this dungeon')
    if any(type(rule[k]) is not int or not 0<=rule[k]<=2**31-1 for k in ('clear_ed','clear_experience')):
        raise ValueError('Invalid dungeon reward amount')
    drop=rule['world_drop']
    # Legacy bag-item plan remains pinned; native immediate food/currency
    # use ground_loot below and never pass through inventory grants.
    if drop!={'template':77000,'quantity':1}:
        raise ValueError('World-drop pickup schema requires additional native verification')
    chances=rule['drop_chances']
    if set(chances)!={'ordinary','boss','chest'}:raise ValueError('Drop source categories')
    for pair in chances.values():
        if (not isinstance(pair,list) or len(pair)!=2 or any(type(v) is not int for v in pair)
                or not 0<=pair[0]<=pair[1] or not 1<=pair[1]<=1000000):raise ValueError('Drop chance bounds')
    return dict(clear_ed=rule['clear_ed'],clear_experience=rule['clear_experience'],
                clear_items=[item_plan(**v) for v in rule['clear_items']],
                world_drop=item_plan(drop['template'],drop['quantity']),provenance='local_policy')


def ground_loot(dungeon_id,npc,run_id,stage,clear_key):
    """Server-issued ground items, native identities with explicit local rates.

    A reviewed per-NPC assignment is required. Unknown enemies get no fallback
    pool. Rates/amounts remain local; current client scripts lack retail tables.
    """
    from els_server.domain.drop_pickup import GROUND_FOOD,GROUND_ED
    dungeon_rewards(dungeon_id)
    if npc['no_drop'] or (not npc['active'] and npc['template']!=20):return []
    policy=_policy()['dungeons'][str(dungeon_id)]['ground_loot']
    if policy['assignment_source']!='local_fallback' or policy['native_probabilities_known'] is not False:raise ValueError('Unverified loot assignment provenance')
    assignment=policy['npc_loot'].get(str(npc['template']),{})
    if set(assignment)-{'coin','food_templates'}:raise ValueError('Unknown NPC loot field')
    pool=assignment.get('food_templates',[])
    if not isinstance(pool,list) or len(set(pool))!=len(pool) or any(type(t) is not int or t not in GROUND_FOOD for t in pool):
        raise ValueError('Unverified ground food pool')
    for template in pool:
        if client_data().item(template)['item_type']!=9:raise ValueError('Not an immediate ground consumable')
    drops=[]
    if 'coin' in assignment:
        coin=assignment['coin']
        if set(coin)!={'template','amount'} or type(coin['template']) is not int or coin['template'] not in GROUND_ED or type(coin['amount']) is not int or not 1<=coin['amount']<=2**31-1:
            raise ValueError('Unverified ground ED policy')
        from els_server.domain.gm_rates import allow_drop
        if allow_drop(run_id,dungeon_id,stage,npc['key']):
            drops.append(dict(template=coin_template(coin['amount']),ed=coin['amount'],quantity=0))
    if pool and should_drop(dungeon_id,npc,run_id,stage,clear_key):
        seed=uuid.UUID(run_id).bytes+f':food:{dungeon_id}:{stage}:{npc["key"]}'.encode()
        template=pool[int.from_bytes(hashlib.sha256(seed).digest(),'big')%len(pool)]
        drops.append(dict(template=template,ed=0,quantity=0))
    return drops


def should_drop(dungeon_id,npc,run_id,stage,clear_key):
    """Stable per-run roll, never rerolled by a duplicate death report.

    Native ACTIVE controls AI, not loot eligibility. Only the verified chest
    template is admitted among inactive objects; gates and NO_DROP never drop.
    Probabilities are an explicit local fallback, not retail rates.
    """
    dungeon_rewards(dungeon_id)
    if npc['no_drop']:return False
    if npc['template']==20:category='chest'
    elif not npc['active']:return False
    elif stage==2 and npc['key']==clear_key:category='boss'
    else:category='ordinary'
    from els_server.domain.gm_rates import chance
    numerator,denominator=chance(category,*_policy()['dungeons'][str(dungeon_id)]['drop_chances'][category])
    if numerator==denominator:return True
    if numerator==0:return False
    seed=uuid.UUID(run_id).bytes
    draw=int.from_bytes(hashlib.sha256(seed+f':{dungeon_id}:{stage}:{npc["key"]}'.encode()).digest(),'big')
    return draw%denominator<numerator


def drop_reference(dungeon_id):
    data=client_data();dungeon=data.dungeon(dungeon_id)
    adjustments=[r for r in data.rules('AdjustDropTableCommon.lua') if isinstance(r,dict) and r.get('DungeonID')==dungeon_id]
    return dict(dungeon_id=dungeon_id,boss_display_pool=dungeon.get('BOSS_DROP_ITEM',{}),
                cumulative_adjustments=adjustments,probabilities_available=False)
