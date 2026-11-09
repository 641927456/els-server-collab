"""Explicit official-name local mapping for the one selected participation box."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

BOX=723680
POLICY='user-approved-cn20260729-role-gear-v1'
DEFINITION_SHA256='379b25572b0479fb7a1c85511bf12bafa59476d88e724a5e547f44c62d1ca9f3'
_enabled=None

def register():
    global _enabled
    raw=(Path(__file__).resolve().parents[1]/'data/boosting2026-participation-gear.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Participation gear definition identity')
    data=json.loads(raw);client=client_data()
    if (data['schema_version']!=1 or data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA
        or data['catalog_sha256']!=client.manifest['catalog_sha256'] or set(data['families'])!=set(map(str,range(1,16)))):
        raise ValueError('Participation gear fixed scope')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.equipment_requirements import catalog
    from els_server.domain.equipment_reforge_rules import expected_options,target
    from els_server.domain.normal_equipment import definitions
    seen=set();box=data['box'];actual=client.item(BOX)
    if box['template']!=BOX or actual['name']!=box['name'] or hashlib.sha256(actual['record']).hexdigest()!=box['record_sha256']:
        raise ValueError('Participation box original identity')
    for key,group in data['families'].items():
        family=int(key)
        if catalog()[0][group['base_class']]['family']!=family or sorted(r['position'] for r in group['outputs'])!=[8,9,10,11]:
            raise ValueError('Participation original class/part scope')
        for row in group['outputs']:
            t=row['template'];d=client.item(t)
            if (t in seen or not 721881<=t<=721940 or t not in definitions() or target(t) is None
                or d['name']!=row['name'] or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']
                or d['record'][0xd2]!=family or d['equip_position']!=row['position']
                or (VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])!=(1,1,1)
                or (row['metadata'],row['group'],row['max_stack'],row['quantity'],row['enhancement'])!=(1,1,1,1,11)
                or row['reforge']!=[21,100,0] or row['reforge_options']!=expected_options(t,21)):
                raise ValueError('Participation gear exact output')
            seen.add(t)
    if seen!=set(range(721881,721941)):raise ValueError('Participation gear identity coverage')
    if _enabled is not None and _enabled!=data:raise ValueError('Cannot replace active participation gear')
    expected=(box['metadata'],4,999)
    if BOX in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[BOX],TEMPLATE_BAG_GROUPS[BOX],TEMPLATE_MAX_STACKS[BOX])!=expected:
        raise ValueError('Participation box inventory registration conflict')
    VERIFIED_TEMPLATES[BOX],TEMPLATE_BAG_GROUPS[BOX],TEMPLATE_MAX_STACKS[BOX]=expected
    _enabled=data
    from els_server.domain.cubes import catalog as cubes
    cubes.cache_clear()

def enabled():return _enabled is not None

def entry():
    return MappingProxyType(dict(template=BOX,selection_count=0,entries=(),participation_gear=True)) if enabled() else None

def outputs_for(unit_class):
    if not enabled():raise ValueError('Participation gear is not registered')
    from els_server.domain.equipment_requirements import catalog
    classes=catalog()[0]
    if type(unit_class) is not int or unit_class not in classes:raise ValueError('Participation owner class')
    rows=_enabled['families'][str(classes[unit_class]['family'])]['outputs']
    return tuple(MappingProxyType({**r,'reforge':tuple(r['reforge']),'reforge_options':tuple(r['reforge_options'])}) for r in rows)

def preview(row,unit_class):
    return tuple(dict(template=r['template'],quantity=1) for r in outputs_for(unit_class)) if row.get('participation_gear') else row['entries']

def cannot_enhance(template):
    # This intrinsic restriction also holds when the activity is disabled.
    # Explicit box restriction from original KIM text. Do not infer the meaning
    # of the historical templates' differing flags bit or affect other items.
    return type(template) is int and 721881<=template<=721940
