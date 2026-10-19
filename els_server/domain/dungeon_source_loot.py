"""Finite old-table compatibility on current actors; never current retail rates."""
import functools,hashlib,json,uuid
from els_server.paths import PROJECT_ROOT

POLICY='legacy-source-loot-compatibility-v1'
DATA_SHA='7e7ac58e6e74e1500c05c3a513a1bf68287510b344c8b48d141bb1e838c07a79'
_raw=(PROJECT_ROOT/'els_server/data/dungeon_source_loot.json').read_bytes()
_scope=json.loads(_raw)
MAPS=frozenset(map(int,_scope['maps']))
TEMPLATES=frozenset(map(int,_scope['items']))

@functools.lru_cache(maxsize=1)
def catalog():
    if hashlib.sha256(_raw).hexdigest()!=DATA_SHA:raise ValueError('Source loot catalog identity')
    c=json.loads(_raw)
    from els_server.game_data import client_data,CLIENT_SHA
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.drop_pickup import GROUND_FOOD
    from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL,descriptor as normal_descriptor
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,item_body
    from els_server.domain.acquisition_policy import require_acquirable
    data=client_data();routes=route_catalog()._data
    material_raw=(PROJECT_ROOT/'els_server/data/manufacture_inventory.json').read_bytes()
    material=json.loads(material_raw)
    if (hashlib.sha256(material_raw).hexdigest()!=c['material_proof_sha256'] or material['reader_consumed']!=304
        or material['reader_cases']!=21734 or material['runtime_sha256']!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'):
        raise ValueError('Source loot inherited native material evidence')
    materials={r['template']:r for r in material['rows'] if r['template'] in (109945,109955)}
    if (c['schema_version']!=1 or c['policy_id']!=POLICY or c['client_sha256']!=CLIENT_SHA
        or c['scale']!=100000000 or c['catalog_sha256']!=data.manifest['catalog_sha256']
        or c['source_sha256']!='09f8a824a6894fc768a2574d07acecfe15443ef78230eee34970915233c9b4f8'
        or hashlib.sha256((PROJECT_ROOT/'els_server/data/client/dungeon_routes.json').read_bytes()).hexdigest()!=c['routes_sha256']):
        raise ValueError('Source loot source/build scope')
    def actors(node):
        if 'options' in node:
            for option in node['options']:yield from actors(option)
        else:yield node
    for key,row in c['maps'].items():
        if key=='30000' or key not in routes['routes']:raise ValueError('Source loot permanent route only')
        graph=routes['graphs'][routes['routes'][key]['source']]
        if row['graph_sha256']!=graph['source_sha256']:raise ValueError('Source loot graph changed')
        for source in row['sources']:
            part=graph['stages'][str(source['stage'])]['parts'][str(source['part'])]
            matches=[a for g in part['groups'] for n in g['npcs'] for a in actors(n)
                     if (a['template'],a['source_index'],a['active'],a['boss'])==(source['template'],source['source_index'],source['active'],source['boss'])
                     and not a['no_drop'] and not a.get('ally') and a.get('team',1)!=0]
            if not matches or not source['active'] and source['template'] not in (20,21,29) or source['row'] not in c['rows']:
                raise ValueError('Source loot declared actor changed')
    for row in [*c['rows'].values(),*({'cases':v} for v in c['groups'].values())]:
        cases=row['cases']
        if (len({e['id'] for e in cases})!=len(cases) or cases!=sorted(cases,key=lambda e:e['id'])
            or any(type(e['ticks']) is not int or e['ticks']<0 or e['kind'] not in ('item','group') for e in cases)
            or sum(e['ticks'] for e in cases)>c['scale']
            or any(e['kind']=='group' and str(e['id']) not in c['groups'] for e in cases)):
            raise ValueError('Source loot lottery shape')
    for key,row in c['items'].items():
        t=int(key);item=data.item(t);require_acquirable(t)
        if row['template']!=t or row['record_sha256']!=hashlib.sha256(item['record']).hexdigest():raise ValueError('Source loot item identity')
        if row['kind']=='immediate-food':
            if t not in GROUND_FOOD or item['item_type']!=9 or row['state']!={}:raise ValueError('Source loot unverified food')
        elif row['kind']=='normal':
            if t not in NORMAL or row['state']!=normal_descriptor(t)['state']:raise ValueError('Source loot normal instance')
        elif row['kind']=='existing-material':
            if t not in materials or materials[t]['record_sha256']!=row['record_sha256']:raise ValueError('Source loot material scope')
            expected=dict(metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],max_stack=TEMPLATE_MAX_STACKS[t])
            if row['state']!=expected or expected['group']!=4:raise ValueError('Source loot material registration')
            sample=dict(uid=1,template=t,metadata=expected['metadata'],group=4,slot=0,count=1)
            if hashlib.sha256(item_body(sample)).hexdigest()!=row['body_sha256']:raise ValueError('Source loot existing material body')
        else:raise ValueError('Source loot instance family')
    return c

def source(identity):
    c=catalog();row=c['maps'].get(str(identity['dungeon']))
    if row is None or row['graph_sha256']!=identity['graph_sha256']:raise ValueError('Source loot map identity')
    matches=[s for s in row['sources'] if (s['stage'],s['part'],s['template'],s['source_index'])==
             (identity['stage'],identity['part'],identity['source_template'],identity['source_index'])]
    if len(matches)!=1:raise ValueError('Source loot actor identity')
    return matches[0]

def context(value):
    keys={'owner','run_id','dungeon','stage','part','visits','npc_key','graph_sha256','source_template','source_index'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('Source loot run context')
    from els_server.storage.character_schema import character_uid
    character_uid(value['owner'])
    if not isinstance(value['run_id'],str) or str(uuid.UUID(value['run_id']))!=value['run_id']:raise ValueError('Source loot server UUID')
    if any(type(value[k]) is not int or not 0<=value[k]<2**31 for k in keys-{'owner','run_id','graph_sha256'}):raise ValueError('Source loot run bounds')
    source(value)
    return dict(value)

def policy_for(identity):
    context(identity);return POLICY

def accepted_source(run,npc):
    if (run.identity not in MAPS or npc.get('dynamic') or npc['no_drop'] or npc.get('ally') or npc.get('team',1)==0
        or not npc['active'] and npc['template'] not in (20,21,29) or not any(n is npc for n in run.current['npcs'])):return False
    try:source(dict(dungeon=run.identity,stage=run.stage,part=run.part,source_template=npc['template'],source_index=npc['source_index'],graph_sha256=run.graph['source_sha256']))
    except ValueError:return False
    return True

def plans(identity,boss,randbelow):
    identity=context(identity);c=catalog();actor=source(identity)
    if type(boss) is not bool or boss!=actor['boss']:raise ValueError('Source loot Boss identity')
    def draw(cases):
        value=randbelow(c['scale'])
        if type(value) is not int or not 0<=value<c['scale']:raise ValueError('Source loot random bound')
        end=0
        for case in cases:
            end+=case['ticks']
            if value<end:return case
        return None
    case=draw(c['rows'][actor['row']]['cases'])
    if case is None:return []
    if case['kind']=='group':case=draw(c['groups'][str(case['id'])])
    if case is None or str(case['id']) not in c['items']:return [] # Preserve blank/unsupported mass; never reroll.
    t=case['id']
    return [dict(template=t,quantity=1,option_groups={},instance_descriptor=c['items'][str(t)])]

def descriptor(template):
    row=catalog()['items'].get(str(template))
    if row is None:raise ValueError('Source loot unadmitted template')
    return json.loads(json.dumps(row))

def grant(db,row,identity):
    context(identity);t=row['template'];expected=descriptor(t)
    if (type(row['quantity']) is not int or row['quantity']!=1 or row.get('option_groups')!={}
        or row.get('instance_descriptor')!=expected):raise ValueError('Source loot saved descriptor')
    if expected['kind']=='immediate-food':return []
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.inventory_state import grant_items
    awarded=grant_items(db,[item_plan(t,1)],identity['owner'])
    if len(awarded)!=1 or awarded[0]['template']!=t:raise ValueError('Source loot registered factory result')
    item=awarded[0]
    if expected['kind']=='normal':
        state=expected['state']
        if item['count']!=1 or item.get('durability')!=state['durability'] or item.get('enhancement',0)!=state['enhancement'] or item.get('option_groups',{})!=state['option_groups']:raise ValueError('Source loot default equipment state')
    elif (item['metadata'],item['group'])!=(expected['state']['metadata'],expected['state']['group']) or not 1<=item['count']<=expected['state']['max_stack']:
        raise ValueError('Source loot current material stack')
    return awarded
