"""Current named wedding rewards, with original item-reader classification."""
from functools import lru_cache
from pathlib import Path
import hashlib,json

DATA_SHA='fd6a0719c47766ced81f675a21bb4d95c21e9bbb90a4135be5bc95f56cc30d0d'


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/wedding_gifts.json').read_bytes()
    data=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    client=client_data()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Wedding gift source identity')
    for row in data['readers']:
        item=client.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or item['metadata']!=row['metadata']:
            raise ValueError('Wedding gift native item changed')
    return data


def definitions():
    data=catalog()
    ids={r['template']for r in data['costumes']}|{r['ITEM_ID']for r in data['custom_books']}|set(range(277184,277188))
    return tuple(r for r in data['readers']if r['template']in ids)


@lru_cache(maxsize=1)
def new_templates():return frozenset(r['template']for r in definitions()if not r['previously_registered'])


def entries():
    return tuple(dict(template=r['template'],selection_count=int(r['template']==277147),
                      wedding_gift_box=True,entries=())for r in catalog()['boxes'])


def outputs_for(template,character,minor):
    from els_server.storage.characters import BASE_CLASSES
    from els_server.domain.character_rules import validate_career_state
    validate_career_state(character)
    if type(minor)is not int or minor not in(0,1)or character['unit_type']!=10 and minor:
        raise ValueError('Wedding reward active side')
    data=catalog();box=next(r for r in data['boxes']if r['template']==template)
    if template==277147:return tuple(dict(template=t,quantity=1)for t in range(277184,277188))
    role=BASE_CLASSES[character['unit_type']]
    native=next((r for r in box['native_random_rule'].values()if isinstance(r,dict)and r.get('m_cUnitClass')==role),None)
    if native is None or not native.get('m_iItemGroupIDForMinorUnit'if minor else'm_iItemGroupID'):
        raise ValueError('Wedding gift does not support the current role/side')
    if template in(277143,277144,277145,277146):
        prefix='白色西装'if template in(277143,277144)else'粉色婚纱'
        matches=[r for r in data['costumes']if r['unit_type']==character['unit_type']
                 and int(r['companion'])==minor and r['name'].startswith(prefix)]
        if len(matches)!=1:raise ValueError('Wedding robe source identity')
        return(dict(template=matches[0]['template'],quantity=1),)
    if template==277153:
        matches=[r for r in data['custom_books']if r['UNIT_TYPE']==character['unit_type']
                 and(r['variant']==3 if minor else r['variant']!=3)]
        if len(matches)!=1:raise ValueError('Wedding sit source identity')
        return(dict(template=matches[0]['ITEM_ID'],quantity=1),dict(template=277155,quantity=200))
    matches=[r for r in data['style_packages']if(r['box'],r['role'],r['minor'])==(template,character['unit_type'],minor)]
    if len(matches)!=1:raise ValueError('Wedding costume package identity')
    return tuple(dict(template=t,quantity=1)for t in matches[0]['contents'])


def selected_outputs(template,character,choices):
    outputs=outputs_for(template,character,character['active_unit'])
    if template!=277147:
        if choices:raise ValueError('Fixed wedding gift has no selection')
        return outputs
    if len(choices)!=1 or choices[0]not in{r['template']for r in outputs}:
        raise ValueError('Select one published wedding costume box')
    return tuple(r for r in outputs if r['template']==choices[0])


def plan_for(template,character,choices,epoch):
    readers={r['template']:r for r in catalog()['readers']};plan=[]
    for output in selected_outputs(template,character,choices):
        r=readers[output['template']];remaining=output['quantity']
        while remaining:
            count=min(99,remaining);remaining-=count
            value=dict(template=r['template'],metadata=r['metadata'],group=r['group'],quantity=count)
            if template in(277143,277145):value['activation_seconds']=30*86400
            elif template in(277184,277185,277186,277187):value['activation_seconds']=86400
            plan.append(value)
    return plan


def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!='wedding-gifts-first-use-20261106-v1':return False
    if(source.kind!='box'or identity.get('definition_sha256')!=DATA_SHA
       or identity.get('owner')!=source.owner):raise ValueError('Wedding gift acquisition source')
    plan=plan_for(identity['template'],identity['character'],tuple(identity['choices']),identity['epoch'])
    source.validate_plan(plan)
    if template not in{r['template']for r in plan}:raise ValueError('Output outside wedding gift')
    return True


def definition_sha(template):
    if template not in{r['template']for r in catalog()['boxes']}:raise ValueError('Unknown wedding gift box')
    return DATA_SHA
