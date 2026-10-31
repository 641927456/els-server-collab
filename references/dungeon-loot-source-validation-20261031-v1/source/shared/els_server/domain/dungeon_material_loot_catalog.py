"""Finite existing material Boss loot; rates/counts are local compatibility."""
import functools
import hashlib
import json
from els_server.paths import PROJECT_ROOT

POLICY='dungeon-material-loot-compatibility-v1'
DATA_SHA='b936d1bb6c786475ac190a073902a823610dcc9847106dd52a8c46b988a7a2ef'
OLD_MAPS=frozenset((33031,33041,33051,33191,33261,34320,34330,34340,34350,34360,34710,34720,34760,34770,34780,34790,34800,35180,35190,41141,41271))
NEW_MAPS=frozenset((34510, 34520, 34530, 34540, 34550, 34560, 34740, 34750, 35350, 35630, 35640, 35890))
MAPS=OLD_MAPS|NEW_MAPS
OLD_TEMPLATES=frozenset((118177,118178,118206,118252,154065,154066))
NEW_TEMPLATES=frozenset((118186, 118376, 118377, 119210, 119211, 136042, 136045, 136047, 136048))
TEMPLATES=OLD_TEMPLATES|NEW_TEMPLATES
# Current CN secret-dungeon tokens are account-weekly clear rewards, not
# random Boss drops. Keep descriptors and saved issue claims compatible.
CLEAR_REWARD_ONLY_MAPS=frozenset((33031,33041,33051,33191,33261,35180,35190,41141,41271))
KIND='ordinary-material-default-v1'
VALUES=dict(boss_percent=25,quantity=1,selection='uniform within this exact finite map COMMON subset',ordinary_extra=False,clear_extra=False)


# Exact local policy contracts, not recovered native string labels.
GENERATION_RULE='material-nine-preserve-probability-designB-local-v1'
GROWTH_EXTENSION={'rule_id': 'material-nine-preserve-probability-designB-local-v1', 'old_hit_coaward_maps': [34320, 34330, 34340, 34350, 34360], 'old_hit_coaward_template': 118186, 'old_hit_trigger_percent': 25, 'shared_extra_draws': 0, 'old_hit_material_rows_max': 2, 'new_twelve_maps': [34510, 34520, 34530, 34540, 34550, 34560, 34740, 34750, 35350, 35630, 35640, 35890], 'new_map_uniform_trigger_percent': 25, 'quantity_per_row': 1, 'note': 'Finite local compatibility: coaward is correlated with original hit. Not retail probability; expected material units on old five rises0.25 to0.5.'}
COAWARD_MAPS=frozenset((34320, 34330, 34340, 34350, 34360))
OLD_MAP_POOLS={33031: [154065, 154066], 33041: [154065, 154066], 33051: [154065, 154066], 33191: [154065, 154066], 33261: [154065, 154066], 34320: [118177, 118178], 34330: [118177], 34340: [118177], 34350: [118177], 34360: [118177], 34710: [118206], 34720: [118206], 34760: [118252], 34770: [118252], 34780: [118252], 34790: [118252], 34800: [118252], 35180: [154065], 35190: [154065], 41141: [154065, 154066], 41271: [154065, 154066]}
NEW_ITEM_CONTRACTS={118186: {'template': 118186, 'item_type': 7, 'metadata': 2, 'group': 4, 'max_stack': 300, 'record_sha256': '7bffc33ae093888a38c4029c1dc99e9fa6afc83a9a9a9c8b381e89921a533692', 'instance_kind': 'material-type7-default-v1', 'default_instance': {'metadata': 2, 'group': 4, 'max_stack': 300, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'dbd92472b2ca5e28023a5256d82e76ab70311220f241695f6ace804e15f07115', 'report_row_pointer': '/rows/0', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': '24182f30b5d88447d970a5661bf2bd7fdc26a5cec86c9485a456d39523fa2dea'}, {'count': 300, 'consumed': 304, 'wire_sha256': 'b66b02a9c2ae6d8753b09b0645d4648512e39e4af97ba1bd71c04913fe4b2aee'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 118376: {'template': 118376, 'item_type': 6, 'metadata': 2, 'group': 3, 'max_stack': 10000, 'record_sha256': '54d6127fafbf8ebe901d491f3704c2caf491b4776aedc4f4fcff345856722bbc', 'instance_kind': 'material-type6-default-v1', 'default_instance': {'metadata': 2, 'group': 3, 'max_stack': 10000, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/4', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'd79dcc163bbc31d08f43d4becb7859a58b75b4cc17382d1564f1f6b5705f4f69'}, {'count': 10000, 'consumed': 304, 'wire_sha256': '1182b639c120190af6bb9642a0c8ff906d2a6af96d083cc650fee253a99b0c6a'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 118377: {'template': 118377, 'item_type': 6, 'metadata': 2, 'group': 3, 'max_stack': 20000, 'record_sha256': '74d79efd67685971417955924d16dc78c5a542524c16b6aa4bccc470d3f3ec21', 'instance_kind': 'material-type6-default-v1', 'default_instance': {'metadata': 2, 'group': 3, 'max_stack': 20000, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/5', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'fe3dda9f9e68bc2d40ca371566ab0b82b171bea062da7b84a03ba0aa2f0588ea'}, {'count': 20000, 'consumed': 304, 'wire_sha256': '2a19303c717ce646e0822a2985c7af6639f56702de8b90ed58395ef8a820041f'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 119210: {'template': 119210, 'item_type': 6, 'metadata': 2, 'group': 3, 'max_stack': 10000, 'record_sha256': '53b51a8908671627db0dbd05e72f82a618c382747c1e5b112cd3db67d3c06cb4', 'instance_kind': 'material-type6-default-v1', 'default_instance': {'metadata': 2, 'group': 3, 'max_stack': 10000, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/6', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'dba21734d351cd9001d4d24e7ff2c2d718ecb9b9c91f40e1c399dff5951bd95d'}, {'count': 10000, 'consumed': 304, 'wire_sha256': 'f0307886e05f381fbeea9a4e015ae7bf174d0247b0eec050ba1a2599753e5782'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 119211: {'template': 119211, 'item_type': 6, 'metadata': 2, 'group': 3, 'max_stack': 20000, 'record_sha256': '32a35e5114d95e361a2a3ad08b0ae5c31eeb9be683659279d0d940b053f5a976', 'instance_kind': 'material-type6-default-v1', 'default_instance': {'metadata': 2, 'group': 3, 'max_stack': 20000, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/7', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': '3a8ddaf237e7adeea3769630e542a6e95326a05aed77ddd5f710ef5aa81b29a8'}, {'count': 20000, 'consumed': 304, 'wire_sha256': 'cea65cadfd8bdc40f24b79cbf6903c8b02dfeac76042009c867d07801fcfa50f'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 136042: {'template': 136042, 'item_type': 7, 'metadata': 2, 'group': 4, 'max_stack': 300, 'record_sha256': 'b724c38c111343077f9df20763eeb19d9cc6e3ad5388f7f6b6799b94f9e77af4', 'instance_kind': 'material-type7-default-v1', 'default_instance': {'metadata': 2, 'group': 4, 'max_stack': 300, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/11', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': '70f9ce6126cda1507e93ad344daf143b2ddfff393eb64ed4a963c02b8c387cec'}, {'count': 300, 'consumed': 304, 'wire_sha256': '6b5b5208117cc19ec275b1971fd0747cec9911eba0b3b0ad556191ba79955ca8'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 136045: {'template': 136045, 'item_type': 7, 'metadata': 2, 'group': 4, 'max_stack': 300, 'record_sha256': 'b4e5876cd74a994edb144e29a13c1883b3d0f4428040cb815720cce451ed3dc0', 'instance_kind': 'material-type7-default-v1', 'default_instance': {'metadata': 2, 'group': 4, 'max_stack': 300, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/14', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'ada511f7e5256400a1800701738cb71893385d9f445c1eb043231f293ac8d9f2'}, {'count': 300, 'consumed': 304, 'wire_sha256': 'd49816871314016646af964e962ddb077392c6859ec41c00a8b429c64a4681c0'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 136047: {'template': 136047, 'item_type': 7, 'metadata': 2, 'group': 4, 'max_stack': 300, 'record_sha256': '7274f40251d6b75ed46a568ebbb494743164aa3c3ff805f14fb7cb0d687e1335', 'instance_kind': 'material-type7-default-v1', 'default_instance': {'metadata': 2, 'group': 4, 'max_stack': 300, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/16', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'bb239903d8da534a0da8b5759a3a80a74f72d26aaee0e9e7e53cc178d4809688'}, {'count': 300, 'consumed': 304, 'wire_sha256': '4d6bba6f23f8778800847666ec0df442d04a2b2376ccc0642f27529d53344d46'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}, 136048: {'template': 136048, 'item_type': 7, 'metadata': 2, 'group': 4, 'max_stack': 300, 'record_sha256': '4e2ca382364843870cd38b1b06637f8f741ef5ceee74a379fc8a68b8b226ad83', 'instance_kind': 'material-type7-default-v1', 'default_instance': {'metadata': 2, 'group': 4, 'max_stack': 300, 'option_groups': {}}, 'inherited_dto_evidence': {'evidence_matrix_sha256': '68c62b04593dfb1ce12305895c84d434d4c091496fee27d2aa9e99170d973a01', 'report_sha256': 'f4d2a0646c51503000ce1ee848937d151402660bc4b394937bceeb926f953717', 'report_row_pointer': '/rows/17', 'historical_image_sha256': 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229', 'count_cases': [{'count': 1, 'consumed': 304, 'wire_sha256': 'adbe2295c467346752924a89d9ce4576585a8f16cbd98d3a810aedfb4cc6cdc0'}, {'count': 300, 'consumed': 304, 'wire_sha256': '33b67304c563e0ef34e6e7137f6c009a8b49f551485599500acf9873932a4b33'}], 'evidence_status': 'inherited-positive-DTO-only', 'cap_plus_one_rejection_proven': False, 'full_CF_D0_D2_D3_consumers_proven': False, 'historical_first_dependency_preimport_closure_proven': False}}}

def _new_item(data,t,row,verified,groups,caps):
    expected=NEW_ITEM_CONTRACTS[t]
    from els_server.domain.inventory_items import LOCAL_MAX_STACK
    item=data.item(t)
    if row!=expected or item['item_type']!=expected['item_type'] or item['metadata']!=2:
        raise ValueError('New material finite class/evidence contract')
    if hashlib.sha256(item['record']).hexdigest()!=expected['record_sha256']:
        raise ValueError('New material original record')
    if t not in verified or (verified[t],groups[t],caps[t])!=(expected['metadata'],expected['group'],max(expected['max_stack'],LOCAL_MAX_STACK)):
        raise ValueError('New material existing registration changed')
    # No cap registration writes, socket field insertion, or RNG calls here.

def _generation_marker(identity,template):
    rule=map_rule(identity['dungeon'])
    if type(template) is not int or template not in NEW_TEMPLATES:
        raise ValueError('Generation marker requires exact new material')
    if identity['dungeon'] in COAWARD_MAPS and template==118186 and rule.get('hit_coaward_templates')==[118186]:
        origin='old-hit-coaward'
    elif identity['dungeon'] in NEW_MAPS and template in rule['finite_common_candidates']:
        origin='new-map-uniform'
    else:raise ValueError('New material cross-map/origin refused')
    return dict(rule_id=GENERATION_RULE,origin=origin,dungeon=identity['dungeon'],template=template)


def _actors(value):
    if 'options' in value:
        for row in value['options']:yield from _actors(row)
    elif 'template' in value:yield value

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/dungeon_material_loot_catalog.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Material loot finite catalog identity')
    c=json.loads(raw)
    if c.get('growth_extension')!=GROWTH_EXTENSION:raise ValueError('New material local draw policy changed')
    from els_server.game_data import client_data,CLIENT_SHA
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,LOCAL_MAX_STACK
    from els_server.domain.dungeon_routes import route_catalog
    data=client_data();routes=route_catalog()._data
    if (c['schema_version']!=1 or c['policy_id']!=POLICY or c['enabled'] is not True or c['client_sha256']!=CLIENT_SHA
        or c['catalog_sha256']!=data.manifest['catalog_sha256'] or c['values']!=VALUES
        or set(map(int,c['maps']))!=MAPS or set(map(int,c['items']))!=TEMPLATES):
        raise ValueError('Material loot finite scope/policy')
    used=set()
    for key,row in c['maps'].items():
        identity=int(key);route=routes['routes'].get(key)
        if route is None or row['dungeon']!=identity or row['route_source']!=route['source']:raise ValueError('Material loot permanent route only')
        graph=routes['graphs'][route['source']];definition=data.dungeon(identity)
        if (row['graph_sha256']!=graph['source_sha256'] or row['definition_sha256']!=hashlib.sha256(data._definition('dungeons','id',identity).encode()).hexdigest()):
            raise ValueError('Material loot graph/definition identity')
        members={v for v in definition.get('BOSS_DROP_ITEM',{}).get('COMMON',{}).values() if type(v) is int and v>0}
        pool=row['finite_common_candidates']
        if not isinstance(pool,list) or not pool or len(pool)!=len(set(pool)) or any(type(t) is not int or t not in TEMPLATES or t not in members for t in pool):
            raise ValueError('Material loot numeric COMMON membership')
        coaward=row.get('hit_coaward_templates',[])
        if identity in OLD_MAPS and pool!=OLD_MAP_POOLS[identity]:raise ValueError('Original material pool changed')
        if identity in COAWARD_MAPS:
            if coaward!=[118186] or 118186 not in members:raise ValueError('Finite old-hit coaward membership')
        elif coaward:raise ValueError('Unadmitted material supplement')
        if identity in NEW_MAPS and any(t not in NEW_TEMPLATES for t in pool):raise ValueError('New map original-six overlap')
        used.update(pool);used.update(coaward);sources=[]
        for stage,st in graph['stages'].items():
            for part,pt in st['parts'].items():
                for group in pt['groups']:
                    for entry in group['npcs']:
                        for actor in _actors(entry):
                            if actor['boss'] and actor['active'] and not actor['no_drop'] and not actor.get('ally') and actor.get('team',1)!=0:
                                signature=dict(stage=int(stage),part=int(part),template=actor['template'],source_index=actor['source_index'])
                                if signature not in sources:sources.append(signature)
        if not sources or row['accepted_boss_sources']!=sources:raise ValueError('Material loot original hostile Boss sources')
    if used!=TEMPLATES:raise ValueError('Material loot unused/unknown item')
    for key,row in c['items'].items():
        t=int(key)
        if t in NEW_TEMPLATES:
            require_acquirable(t);_new_item(data,t,row,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS)
            continue
        item=data.item(t);require_acquirable(t)
        expected=dict(metadata=2,group=3,max_stack=99,option_groups={})
        if (t not in VERIFIED_TEMPLATES or row['template']!=t or row['item_type']!=6 or item['item_type']!=6
            or row['record_sha256']!=hashlib.sha256(item['record']).hexdigest()
            or (row['metadata'],row['group'],max(row['max_stack'],LOCAL_MAX_STACK))!=(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])
            or (row['metadata'],row['group'],row['max_stack'])!=(2,3,99) or row['instance_kind']!=KIND or row['default_instance']!=expected):
            raise ValueError('Material loot original registered instance class')
        proof=row['native_proof']
        if (proof['image_sha256']!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
            or proof['d0_branches']!=20 or proof['cf_d2_d3_count99_and_split1'] is not True):
            raise ValueError('Material loot original native evidence')
    return c

def map_rule(identity):
    if type(identity) is not int or identity not in MAPS:raise ValueError('Material loot unadmitted map')
    return catalog()['maps'][str(identity)]

def descriptor(template):
    if type(template) is not int or template not in TEMPLATES:raise ValueError('Material loot unadmitted template')
    row=catalog()['items'][str(template)]
    return dict(kind=row['instance_kind'] if template in NEW_TEMPLATES else KIND,record_sha256=row['record_sha256'],state=json.loads(json.dumps(row['default_instance'])))

def validate_issued(row,identity):
    rule=map_rule(identity['dungeon']);t=row['template']
    allowed=rule['finite_common_candidates']+rule.get('hit_coaward_templates',[])
    if (type(t) is not int or t not in allowed or type(row['quantity']) is not int or row['quantity']!=1
        or row.get('option_groups')!={} or row.get('instance_descriptor')!=descriptor(t)):
        raise ValueError('Material loot saved default descriptor')
    if t in NEW_TEMPLATES:
        marker=row.get('material_generation')
        if marker!=_generation_marker(identity,t) or any(type(marker[k]) is not int for k in ('dungeon','template')):
            raise ValueError('New material generation marker refused')
    elif 'material_generation' in row:raise ValueError('Generation marker is only for new nine materials')


def accepted_source(run,npc):
    if run.identity not in MAPS:return False
    rule=map_rule(run.identity)
    return bool(run.graph['source_sha256']==rule['graph_sha256'] and npc.get('boss') and npc.get('active')
        and not npc.get('no_drop') and not npc.get('ally') and npc.get('team',1)!=0 and not npc.get('dynamic')
        and any(n is npc for n in run.current['npcs'])
        and dict(stage=run.stage,part=run.part,template=npc['template'],source_index=npc['source_index']) in rule['accepted_boss_sources'])

def plans(identity,boss,randbelow,*,drop_bp=0):
    rule=map_rule(identity['dungeon'])
    if type(boss) is not bool:raise ValueError('Material loot Boss category')
    if not boss:return []
    if identity['dungeon'] in CLEAR_REWARD_ONLY_MAPS:return []
    def draw(size):
        value=randbelow(size)
        if type(value) is not int or not 0<=value<size:raise ValueError('Material loot random result bound')
        return value
    if not __import__('els_server.domain.elixir_economy',fromlist=['hit']).hit(25,100,randbelow,drop_bp):return []
    pool=rule['finite_common_candidates'];t=pool[draw(len(pool))]
    rows=[dict(template=t,quantity=1,option_groups={},instance_descriptor=descriptor(t))]
    if t in NEW_TEMPLATES:rows[0]['material_generation']=_generation_marker(identity,t)
    for extra in rule.get('hit_coaward_templates',[]):
        rows.append(dict(template=extra,quantity=1,option_groups={},instance_descriptor=descriptor(extra),material_generation=_generation_marker(identity,extra)))
    return rows
