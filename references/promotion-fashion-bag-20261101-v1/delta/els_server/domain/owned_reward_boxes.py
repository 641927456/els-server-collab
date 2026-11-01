"""Owned Essence pouch and class-specific Force choices from published contents."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

BOXES=frozenset((117542,135666,135871,723618,723687,723688))
DATA_SHA='3ed67020222f3106c97dea75c4224937c1094aef71ba7c247b95d518a2ca7321'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/owned_reward_boxes.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Owned reward box definition identity')
    data=json.loads(raw);client=client_data()
    if data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Owned reward box client identity')
    boxes={r['template']:r for r in data['boxes']}
    if set(boxes)!=BOXES:raise ValueError('Owned reward box scope')
    for row in (*data['boxes'],*data['readers']):
        item=client.item(row['template'])
        if item['name']!=row['name'] or item['metadata']!=row['metadata'] or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:
            raise ValueError('Owned reward box item identity')
    from els_server.domain.fashion_inventory import native_groups
    return dict(data,readers=native_groups(data['readers']))

def definitions():return (*catalog()['boxes'],*catalog()['readers'])

def entries():
    return tuple(MappingProxyType(dict(template=r['template'],selection_count=r['selection_count'],
        entries=(),owned_reward_box=True))for r in catalog()['boxes'])

def outputs_for(template,character):
    row=next(r for r in catalog()['boxes']if r['template']==template)
    if template in(117542,723618):return tuple(row['class_outputs']['0'])
    from els_server.domain.character_rules import validate_career_state
    validate_career_state(character)
    outputs=row['class_outputs'].get(str(character['unit_class']))
    if outputs is None:raise ValueError('Reward box does not support the current class')
    if template in(723687,723688)and character['level']!=99:raise ValueError('Force choice requires level 99')
    return tuple(outputs)

def selected_outputs(template,character,choices):
    outputs=outputs_for(template,character)
    if template not in(723687,723688):
        if choices:raise ValueError('Fixed reward box does not accept choices')
        return outputs
    if len(choices)!=1:raise ValueError('Select exactly one Force book')
    selected=tuple(r for r in outputs if r['template']==choices[0])
    if not selected:raise ValueError('Force choice is outside the current class')
    return selected

@functools.lru_cache(maxsize=1)
def new_templates():return frozenset(r['template']for r in catalog()['readers']if not r['previously_registered'])

def plan_for(template,character,choices,epoch):
    readers={r['template']:r for r in catalog()['readers']};plan=[]
    for output in selected_outputs(template,character,choices):
        row=readers[output['template']]
        item=dict(template=row['template'],metadata=row['metadata'],group=row['group'],quantity=output['quantity'])
        if output.get('inventory_days'):item['expires_at']=epoch+output['inventory_days']*86400
        plan.append(item)
    return plan

def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!='owned-reward-boxes-20261031-v1':return False
    if source.kind!='box'or identity.get('definition_sha256')!=DATA_SHA or identity.get('owner')!=source.owner:
        raise ValueError('Owned reward box acquisition source')
    plan=plan_for(identity['template'],identity['character'],tuple(identity['choices']),identity['epoch'])
    source.validate_plan(plan)
    if template not in {r['template']for r in plan}:raise ValueError('Output outside owned reward box')
    return True

def finalize_grants(db,owner,grants,outputs):
    """Known fixed artifact lines replace the shared factory's pending state."""
    presets={r['template']:r['option_groups']for r in outputs if 'option_groups'in r}
    if not presets:return
    from els_server.storage.equipment_options import replace as replace_options
    from els_server.storage.equipment_identification import replace as replace_identified
    for item in grants:
        groups=presets[item['template']]
        replace_options(db,owner,item['uid'],item.get('option_groups',{}),groups)
        replace_identified(db,owner,item['uid'],False,True)
