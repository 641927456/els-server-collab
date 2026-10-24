"""Three official90-day role/minor-specific reward sets, opt-in registration."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
BOXES=frozenset((721780,723613,723614))
POLICY='user-approved-cn20260729-role-fashion90-v1'
DEFINITION_SHA256='481d8d339eddb433262399df1795aaa47f42d051c6a556a9ab27570530bc82ec'
_enabled=None

def register():
    global _enabled
    raw=(Path(__file__).resolve().parents[1]/'data/boosting2026-fashion90.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Role fashion90 definition identity')
    data=json.loads(raw);client=client_data()
    if data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Role fashion90 fixed client')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks,FASHION_EQUIP_SLOTS as slots,FASHION_POSITIONS,GM_DERIVED_TEMPLATES
    from els_server.domain.companion_fashion import resolve_slots
    definitions={};policies={};expected_keys={str(f)+':0' for f in range(1,16)}|{'10:1'}
    for box in data['boxes']:
        t=box['template']
        if t not in BOXES or t in definitions or box['period_days']!=90 or set(box['cohorts'])!=expected_keys:raise ValueError('Role fashion90 exact scope')
        if hashlib.sha256(client.item(t)['record']).hexdigest()!=box['record_sha256']:raise ValueError('Role fashion90 original box')
        for key,cohort in box['cohorts'].items():
            family,minor=map(int,key.split(':'));outputs=cohort['outputs']
            if len(outputs)!=(11 if t==721780 else 4) or len({r['template'] for r in outputs})!=len(outputs):raise ValueError('Role fashion90 complete set')
            for row in outputs:
                item=client.item(row['template']);record=item['record'];slot=resolve_slots({row['template']:FASHION_POSITIONS[item['equip_position']]})[row['template']]
                if (item['name']!=row['name'] or hashlib.sha256(record).hexdigest()!=row['record_sha256'] or record[210]!=family
                    or bool(record[8]&4)!=bool(minor) or (row['role'],row['minor'])!=(family,bool(minor))
                    or (row['metadata'],row['group'],row['max_stack'],row['quantity'],row['slot'])!=(item['metadata'],27,1,1,slot)
                    or not record[4]&1 or record[4]&32):raise ValueError('Role fashion90 original item/slot/class')
                policy=(row['metadata'],27,1,slot);identity=row['template']
                if identity in policies and policies[identity]!=policy:raise ValueError('Role fashion90 conflicting class policy')
                if identity in meta and identity not in GM_DERIVED_TEMPLATES and ((meta[identity],groups[identity],stacks[identity])!=policy[:3] or slots.get(identity)!=slot):raise ValueError('Role fashion90 existing registration conflict')
                policies[identity]=policy
        definitions[t]=box
    if set(definitions)!=BOXES or len(policies)!=304:raise ValueError('Role fashion90 full output coverage')
    if _enabled is not None and _enabled!=definitions:raise ValueError('Cannot replace registered fashion90 definition')
    for t,(metadata,group,stack,slot) in policies.items():meta[t]=metadata;groups[t]=group;stacks[t]=stack;slots[t]=slot
    _enabled=definitions
    from els_server.domain.cubes import catalog
    catalog.cache_clear()

def entries():
    return tuple(MappingProxyType(dict(template=t,selection_count=0,entries=(),role_fashion90=True)) for t in sorted(_enabled or {}))

def outputs_for(template,unit_class,active):
    if _enabled is None or template not in _enabled:raise ValueError('Role fashion90 not registered')
    from els_server.domain.equipment_requirements import catalog
    classes=catalog()[0]
    if type(unit_class) is not int or unit_class not in classes or type(active) is not int or active not in (0,1):raise ValueError('Role fashion90 character identity')
    family=classes[unit_class]['family']
    if family!=10 and active:raise ValueError('Foreign role cannot select LuCiel minor rewards')
    return tuple(MappingProxyType(dict(r)) for r in _enabled[template]['cohorts'][str(family)+':'+str(active)]['outputs'])

def preview(template,character,flag):
    active=character.get('luciel_active_unit',0) if character['unit_type']==10 else 0
    if flag!=active:raise ValueError('Role fashion90 preview active state mismatch')
    return tuple(dict(template=r['template'],quantity=1) for r in outputs_for(template,character['unit_class'],active))
