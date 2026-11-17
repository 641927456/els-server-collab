"""Owned fixed boxes and the explicitly approved finite local reward rules."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='b83f1a75b31270ce3e79f946b8ea0a6a8bf21e814e91024d00333e66cb62837a'
POLICY='retained-fixed-box-openings-20261108-v1'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/retained_box_openings.json').read_bytes()
    data=json.loads(raw);client=client_data()
    if (hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['client_sha256']!=CLIENT_SHA
        or data['catalog_sha256']!=client.manifest['catalog_sha256']):
        raise ValueError('Retained fixed box definitions changed')
    for row in (*data['boxes'],*data['outputs']):
        item=client.item(row['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or (item['name'],item['metadata'])!=(row['name'],row['metadata'])):
            raise ValueError('Retained fixed box native item changed')
    return data

@functools.lru_cache(maxsize=1)
def boxes():return MappingProxyType({r['template']:r for r in catalog()['boxes']})

def entries():
    return tuple(MappingProxyType(dict(template=r['template'],group=4,selection_count=0,
        entries=r['outputs'],resurrection_gain=r.get('resurrection_gain',0),
        retained_fixed_box=True,retained_role_box=r.get('role_box',False)or bool(r.get('branches')),
        retained_local_box=bool(r.get('branches')),retained_key_box=any(b['key']for b in r.get('branches',())),
        retained_active_side=(any('active_unit'in b for b in r['branches'])if r.get('branches')else r.get('role_box',False))))for r in boxes().values())

def reader_definitions():return tuple(r for r in catalog()['outputs']if r['new_reader'])

@functools.lru_cache(maxsize=1)
def private_templates():return frozenset(r['template']for r in catalog()['outputs']if r['source_only'])

@functools.lru_cache(maxsize=1)
def new_templates():return frozenset(r['template']for r in catalog()['outputs']if r['new_reader']or r.get('new_acquisition',False))

def require_usable(template,character,item):
    row=boxes()[template]
    if character['level']<row['minimum_level']:raise ValueError('Retained fixed box minimum level')
    if item.get('sealed',False):raise ValueError('Unseal retained fixed box before opening')
    if row.get('role_box')or row.get('branches'):outputs_for(template,character)

def _matches(branch,character):
    return (('families'not in branch or character['unit_type']in branch['families'])
        and('classes'not in branch or character['unit_class']in branch['classes'])
        and('active_unit'not in branch or character.get('active_unit',0)==branch['active_unit']))

def branches_for(template,character):
    result=[b for b in boxes()[template]['branches']if _matches(b,character)]
    if not result:raise ValueError('Owned box has no rule for this character')
    return result

def preview_outputs(template,character,keys=()):
    branches=branches_for(template,character);requested=set(keys)-{0}
    row=boxes()[template];aliases=row.get('key_aliases',{})
    known={b['key']for b in row['branches']}|{int(k)for k in aliases}
    if requested-known:raise ValueError('Owned box preview key is not registered')
    requested={aliases.get(str(k),k)for k in requested}
    outputs={}
    for branch in branches:
        if requested and branch['key']not in requested:continue
        for row in branch['outputs']:outputs.setdefault(row['template'],row)
    if not outputs:raise ValueError('Owned box preview key has no character rule')
    return tuple(outputs.values())

def branch_for(template,character,key):
    selected=[b for b in branches_for(template,character)if b['key']==key]
    if len(selected)!=1:raise ValueError('Owned box key rule is not unique')
    return selected[0]

def selected_outputs(branch,roll):
    if not branch['random']:
        if roll is not None:raise ValueError('Fixed owned box does not draw')
        return branch['outputs']
    total=sum(r['weight']for r in branch['outputs'])
    if type(roll)is not int or not 0<=roll<total:raise ValueError('Owned box random source out of range')
    for row in branch['outputs']:
        if roll<row['weight']:return(row,)
        roll-=row['weight']

def draw_outputs(branch,randbelow):
    roll=randbelow(sum(r['weight']for r in branch['outputs']))if branch['random']else None
    return selected_outputs(branch,roll),roll

def outputs_for(template,character=None):
    row=boxes()[template]
    if row.get('branches'):return preview_outputs(template,character)
    if not row.get('role_box'):return row['outputs']
    if 'allowed_classes'in row and character['unit_class']not in row['allowed_classes']:raise ValueError('Retained box requires a registered exact class')
    from els_server.domain.equipment_requirements import class_matches
    selected=[r for r in row['outputs']if class_matches(character['unit_class'],r['unit_class'])
        and r.get('active_unit',character.get('active_unit',0))==character.get('active_unit',0)]
    if len(selected)!=1:raise ValueError('Retained box has no exact output for this character')
    return selected

@functools.lru_cache(maxsize=1)
def output_map():return {r['template']:r for r in catalog()['outputs']}

def plan_from_outputs(selected,epoch):
    outputs=output_map()
    result=[]
    for row in selected:
        item=dict(template=row['template'],metadata=outputs[row['template']]['metadata'],
            group=outputs[row['template']]['group'],quantity=row['quantity'])
        if row.get('inventory_days'):
            from els_server.domain.item_expiration import validate
            if type(epoch)is not int:raise ValueError('Retained fixed box opening clock required')
            item['expires_at']=validate(epoch+86400*row['inventory_days'])
        result.append(item)
    return result

def plan_for(template,epoch=None,character=None,key=0,roll=None):
    selected=selected_outputs(branch_for(template,character,key),roll)if boxes()[template].get('branches')else outputs_for(template,character)
    return plan_from_outputs(selected,epoch)

def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    if (source.kind!='box' or identity.get('definition_sha256')!=DATA_SHA
        or identity.get('owner')!=source.owner or identity.get('box_debit')!=1):
        raise ValueError('Retained fixed box acquisition identity')
    if boxes()[identity['template']].get('branches'):
        branch=branch_for(identity['template'],identity['character'],identity['key'])
        if identity.get('key_debit')!=branch['key_count']:raise ValueError('Owned box key debit identity')
    source.validate_plan(plan_for(identity['template'],identity.get('epoch'),identity.get('character'),identity.get('key',0),identity.get('roll')))
    source.validate_template(template)
    return True
