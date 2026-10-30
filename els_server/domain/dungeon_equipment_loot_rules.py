"""Finite dungeon equipment acquisition; explicitly compatible rates/counts."""
import functools
import hashlib
import json
import secrets
import uuid
from els_server.paths import PROJECT_ROOT

POLICY='dungeon-equipment-loot-compatibility-v1'
LEGACY_TEMPLATES=frozenset((118518,118519,118544,118545,118445,118638))
# Existing LocalSession dispatches this finite routing set to atomic claim.
# Legacy catalog/pools remain pinned to the original six templates below.
from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL_LOOT_TEMPLATES
from els_server.domain.dungeon_material_loot_catalog import MAPS as MATERIAL_MAPS,TEMPLATES as MATERIAL_LOOT_TEMPLATES
TEMPLATES=LEGACY_TEMPLATES|NORMAL_LOOT_TEMPLATES|MATERIAL_LOOT_TEMPLATES
MAPS=frozenset((35340,35360,35390,35400))
DATA_SHA='31a5c4c5d7a677f67d01744cc76570c46ca503a9a4fa7d1b30dc3b2ef656eea5'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/dungeon_equipment_loot.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Equipment loot policy identity')
    c=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,LOCAL_MAX_STACK
    from els_server.domain.acquisition_policy import require_acquirable
    if c['policy_id']!=POLICY or c['schema_version']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Equipment loot source identity')
    if set(map(int,c['items']))!=LEGACY_TEMPLATES or set(map(int,c['maps']))!=MAPS:raise ValueError('Equipment loot finite scope')
    for key,row in c['items'].items():
        template=int(key);item=client_data().item(template);require_acquirable(template)
        if (row['template']!=template or template not in VERIFIED_TEMPLATES or row['record_sha256']!=hashlib.sha256(item['record']).hexdigest()
            or (row['metadata'],row['group'],row['max_stack'] if row['max_stack']==1 else max(row['max_stack'],LOCAL_MAX_STACK))!=(VERIFIED_TEMPLATES[template],TEMPLATE_BAG_GROUPS[template],TEMPLATE_MAX_STACKS[template])):raise ValueError('Equipment loot finite item record')
    return c

def context(value):
    if not isinstance(value,dict) or set(value)!={'owner','run_id','dungeon','stage','part','visits','npc_key','graph_sha256'}:raise ValueError('Loot run identity')
    from els_server.storage.character_schema import character_uid
    character_uid(value['owner'])
    if not isinstance(value['run_id'],str) or str(uuid.UUID(value['run_id']))!=value['run_id']:raise ValueError('Loot server run UUID')
    if any(type(value[k]) is not int or not 0<=value[k]<2**31 for k in ('dungeon','stage','part','visits','npc_key')):raise ValueError('Loot run bounds')
    if value['dungeon'] in MAPS:
        row=catalog()['maps'].get(str(value['dungeon']))
        source=row['graph_source_sha256'] if row is not None else None
    elif value['dungeon'] in MATERIAL_MAPS:
        from els_server.domain.dungeon_material_loot_catalog import map_rule as material_map
        source=material_map(value['dungeon'])['graph_sha256']
    else:
        from els_server.domain.dungeon_loot_catalog import map_rule
        source=map_rule(value['dungeon'])['graph_sha256']
    if source!=value['graph_sha256']:raise ValueError('Loot admitted graph identity')
    return dict(value)

def policy_for(identity):
    if identity['dungeon'] in MAPS:return POLICY
    if identity['dungeon'] in MATERIAL_MAPS:
        from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY,map_rule as material_map
        material_map(identity['dungeon'])
        return MATERIAL_POLICY
    from els_server.domain.dungeon_loot_catalog import POLICY as NORMAL_POLICY,map_rule
    map_rule(identity['dungeon'])
    return NORMAL_POLICY

def integer_draw(size,randbelow):
    value=randbelow(size)
    if type(value) is not int or not 0<=value<size:raise ValueError('Loot random result bound')
    return value

def plans(identity,boss,randbelow=secrets.randbelow):
    identity=context(identity)
    if identity['dungeon'] in MATERIAL_MAPS:
        from els_server.domain.dungeon_material_loot_catalog import plans as material_plans
        return material_plans(identity,boss,randbelow)
    if identity['dungeon'] not in MAPS:
        from els_server.domain.dungeon_loot_catalog import plans as normal_plans
        return normal_plans(identity,boss,randbelow)
    if type(boss) is not bool:raise ValueError('Loot source boss flag')
    c=catalog();values=c['values']
    if boss:
        if integer_draw(100,randbelow)>=values['boss_extra_item_percent']:return []
        pool=c['maps'][str(identity['dungeon'])]['finite_boss_candidates']
        template=pool[integer_draw(len(pool),randbelow)]
        if template==118638:
            from els_server.domain.equipment_chip_rules import generate as chip_generate
            options=chip_generate(randbelow)
        else:
            from els_server.domain.equipment_circuit_rules import generate
            options=generate(template,randbelow)
        return [dict(template=template,quantity=1,option_groups=options)]
    if integer_draw(100,randbelow)>=values['ordinary_fragment_percent']:return []
    return [dict(template=118445,quantity=values['ordinary_fragment_quantity'],option_groups={})]

def inventory_plan(template,quantity):
    if template in MATERIAL_LOOT_TEMPLATES:
        from els_server.domain.dungeon_material_loot_catalog import descriptor as material_descriptor
        material_descriptor(template)
        if type(quantity) is not int or quantity!=1:raise ValueError('Material loot single issued quantity')
        from els_server.domain.reward_rules import item_plan
        return item_plan(template,quantity)
    from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL_TEMPLATES,descriptor
    if template in NORMAL_TEMPLATES:
        descriptor(template)
        if type(quantity) is not int or quantity!=1:raise ValueError('Normal loot single default instance')
        from els_server.domain.reward_rules import item_plan
        return item_plan(template,quantity)
    row=catalog()['items'].get(str(template))
    if row is None:raise ValueError('Unissued loot template')
    from els_server.domain.reward_rules import item_plan
    return item_plan(template,quantity)
