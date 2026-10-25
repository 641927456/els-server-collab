"""Finite normal-equipment boss loot; explicit local compatibility policy."""
import functools
import hashlib
import json
from els_server.paths import PROJECT_ROOT

POLICY='dungeon-normal-loot-compatibility-v1'
DATA_SHA='b835c7dc350dc80f5cf198f1c28b4a231daef35544aad4131ab48ace2ad5575f'
MAPS=frozenset((30282,33202,33232,33252,34220,34230,34240,34250,34260,34270,34280,34290,34300,34600,34610,34620,34640,34650,34660,34670,34680,120000))
TEMPLATES=frozenset((30206,30249,30268,30273,186682,186683,186684,186685,11022332,11022336,11022339,11022343,11022344,11022351,11022352,11022359,11022360,11022367,11022368,11022375,11022376,11022383,11022384,11022391,11022392,11022399,11022428,11022432,11022435,11022439,11022440,11022447,11022456,11022463,11022464,11022471,11022472,11022479,11022480,11022487,11022488,11022495))
KIND='normal-equipment-default-v1'

def _actors(value):
    if 'options' in value:
        for option in value['options']:yield from _actors(option)
    elif 'template' in value:yield value

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/dungeon_loot_catalog.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Normal loot finite catalog identity')
    c=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.equipment_durability import maximum
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,item_body
    from els_server.domain.dungeon_routes import route_catalog
    data=client_data();routes=route_catalog()._data;normal=definitions()
    if (c['schema_version']!=1 or c['policy_id']!=POLICY or c['enabled'] is not True or c['client_sha256']!=CLIENT_SHA
        or c['catalog_sha256']!=data.manifest['catalog_sha256'] or set(map(int,c['maps']))!=MAPS or set(map(int,c['items']))!=TEMPLATES
        or c['values']!={'boss_percent':25,'quantity':1,'selection':'uniform within this exact finite map COMMON subset','ordinary_extra':False,'clear_extra':False}):
        raise ValueError('Normal loot finite scope/policy')
    if (hashlib.sha256((PROJECT_ROOT/'els_server/data/client/dungeon_routes.json').read_bytes()).hexdigest()!=c['route_payload_sha256']
        or hashlib.sha256((PROJECT_ROOT/'analysis/integration-20261015/normal-equipment-native.json').read_bytes()).hexdigest()!=c['normal_proof_sha256']):
        raise ValueError('Normal loot route/instance proof identity')
    used=set()
    for key,row in c['maps'].items():
        identity=int(key);route=routes['routes'].get(key)
        if route is None or row['dungeon']!=identity or row['route_source']!=route['source']:raise ValueError('Normal loot permanent route only')
        graph=routes['graphs'][route['source']];definition=data.dungeon(identity)
        if (row['graph_sha256']!=graph['source_sha256'] or row['definition_sha256']!=hashlib.sha256(data._definition('dungeons','id',identity).encode()).hexdigest()):
            raise ValueError('Normal loot source graph/definition')
        common=definition.get('BOSS_DROP_ITEM',{}).get('COMMON',{})
        members={v for v in common.values() if type(v) is int and v>0}
        pool=row['finite_common_candidates']
        if (not isinstance(pool,list) or not pool or len(pool)!=len(set(pool)) or any(type(t) is not int or t not in TEMPLATES or t not in members for t in pool)):
            raise ValueError('Normal loot numeric COMMON membership')
        used.update(pool);sources=[]
        for stage,st in graph['stages'].items():
            for part,pt in st['parts'].items():
                for group in pt['groups']:
                    for entry in group['npcs']:
                        for actor in _actors(entry):
                            if actor['boss'] and actor['active'] and not actor['no_drop'] and not actor.get('ally') and actor.get('team',1)!=0:
                                signature=dict(stage=int(stage),part=int(part),template=actor['template'],source_index=actor['source_index'])
                                if signature not in sources:sources.append(signature)
        if not sources or row['accepted_boss_sources']!=sources:raise ValueError('Normal loot original hostile Boss sources')
    if used!=TEMPLATES:raise ValueError('Normal loot unused/unknown item')
    for key,row in c['items'].items():
        t=int(key);item=data.item(t);require_acquirable(t)
        expected=dict(durability=maximum(t),enhancement=0,option_groups={})
        if (t not in normal or t not in VERIFIED_TEMPLATES or row['template']!=t or item['item_type'] not in (1,2)
            or row['item_type']!=item['item_type'] or row['record_sha256']!=hashlib.sha256(item['record']).hexdigest()
            or (row['metadata'],row['group'],row['max_stack'])!=(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])
            or (row['metadata'],row['group'],row['max_stack'])!=(1,1,1) or row['instance_kind']!=KIND or row['default_instance']!=expected):
            raise ValueError('Normal loot admitted default item class')
        sample=dict(uid=1,template=t,metadata=1,group=1,slot=0,count=1,durability=expected['durability'])
        proof=row['native_proof']
        if (proof['d0_branches']!=20 or proof['cf_bytes']!=54 or proof['d2_bytes']!=50 or proof['d3_records']!=1
            or proof['default_item_body_sha256']!=hashlib.sha256(item_body(sample)).hexdigest()
            or proof['native_image_sha256']!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'):
            raise ValueError('Normal loot original ground/inventory witness')
    return c

def map_rule(identity):
    if type(identity) is not int or identity not in MAPS:raise ValueError('Normal loot unadmitted map')
    return catalog()['maps'][str(identity)]

def descriptor(template):
    if type(template) is not int or template not in TEMPLATES:raise ValueError('Normal loot unadmitted template')
    row=catalog()['items'][str(template)]
    return dict(kind=KIND,record_sha256=row['record_sha256'],state=json.loads(json.dumps(row['default_instance'])))

def validate_issued(row,identity):
    t=row['template'];rule=map_rule(identity['dungeon'])
    if (t not in rule['finite_common_candidates'] or type(row['quantity']) is not int or row['quantity']!=1
        or row.get('option_groups')!={} or row.get('instance_descriptor')!=descriptor(t)):
        raise ValueError('Normal loot saved default descriptor')

def accepted_source(run,npc):
    if run.identity not in MAPS:return False
    rule=map_rule(run.identity)
    return bool(run.graph['source_sha256']==rule['graph_sha256'] and npc.get('boss') and npc.get('active')
        and not npc.get('no_drop') and not npc.get('ally') and npc.get('team',1)!=0 and not npc.get('dynamic')
        and any(n is npc for n in run.current['npcs'])
        and dict(stage=run.stage,part=run.part,template=npc['template'],source_index=npc['source_index']) in rule['accepted_boss_sources'])

def plans(identity,boss,randbelow):
    rule=map_rule(identity['dungeon'])
    if type(boss) is not bool:raise ValueError('Normal loot Boss category')
    if not boss:return []
    def draw(size):
        value=randbelow(size)
        if type(value) is not int or not 0<=value<size:raise ValueError('Normal loot random result bound')
        return value
    if draw(100)>=25:return []
    pool=rule['finite_common_candidates'];t=pool[draw(len(pool))]
    return [dict(template=t,quantity=1,option_groups={},instance_descriptor=descriptor(t))]
