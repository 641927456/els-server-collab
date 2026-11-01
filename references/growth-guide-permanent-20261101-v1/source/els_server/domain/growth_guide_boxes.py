"""Owner-approved fixed CN contents bound to current native item templates."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/growth_guide_boxes.json';raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=json.loads(p.with_suffix('.manifest.json').read_bytes())['payload_sha256']:
        raise ValueError('Guide fixed mapping identity')
    d=json.loads(raw);c=client_data()
    if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:
        raise ValueError('Guide fixed mapping client')
    for r in d['items']:
        if hashlib.sha256(c.item(r['template'])['record']).hexdigest()!=r['record_sha256']:
            raise ValueError('Guide fixed mapping native template')
    return d

def boxes():return {b['template']:b for b in catalog()['boxes']}

def outputs_for(template,character):
    b=boxes()[template]
    from els_server.domain.character_rules import CLASSES
    role=CLASSES[character['unit_class']]
    if b['use_condition']==3 and role['stage']<2:raise ValueError('Guide weapon requires second job')
    active=character.get('luciel_active_unit',0) if character['unit_type']==10 else 0
    return tuple(dict(r) for r in b['outputs'] if not b.get('role') or
        r.get('unit_type') in (0,character['unit_type']) and (r.get('minor') is None or r['minor']==bool(active)))

def entries():
    return tuple(dict(template=b['template'],selection_count=b['selection_count'],entries=b['outputs'],growth_guide=True) for b in catalog()['boxes'])

def plans_for(outputs,now):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    return [dict(template=r['template'],metadata=VERIFIED_TEMPLATES[r['template']],group=TEMPLATE_BAG_GROUPS[r['template']],quantity=r['quantity'],
        **({'enhancement':r['enhancement']} if r.get('enhancement') else {}),
        **({'expires_at':now+r['period_days']*86400} if r.get('period_days') else {})) for r in outputs]

def validate_grants(context,plan):
    template,character,choices,now=context
    rows=outputs_for(template,character);b=boxes()[template]
    if b['selection_count']:
        if len(choices)!=1:raise ValueError('Guide box requires one player choice')
        rows=tuple(r for r in rows if r['template']==choices[0])
        if len(rows)!=1:raise ValueError('Guide choice outside native contents')
    elif choices:raise ValueError('Guide fixed box accepts no choice')
    if plan!=plans_for(rows,now):raise ValueError('Guide fixed grant plan mismatch')
    from els_server.domain.acquisition_policy import excluded_equipment
    if any(p['template'] in excluded_equipment() for p in plan):raise ValueError('Guide legacy item excluded')
    return rows
