"""Verified ordinary-town wear prerequisites; move/instance rules remain separate.

The 868240 predicate covers permitted-use flags, level and three restriction
modes. Right-click subsequently checks D3 independently and item usability.
Never apply the client's special global mode or caller -1 level bypass here.
"""
import functools,hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.equipment_requirements import catalog as classes_and_slots,class_matches
from els_server.domain.normal_equipment import definitions


def _allowed(row,unit_class,level):
    family=classes_and_slots()[0][unit_class]['family'];mode=row['mode']
    if not row['flags4']&0xf00 or level<row['level']:return False
    if mode==1:
        return (row['flags8']>>3)&31!=2 or bool(row['generic_model']) or bool(row['models'][str(family)])
    if mode==2:return family==row['unit_type']
    if mode==3:return class_matches(unit_class,row['unit_class'])
    return False


def validate_proof(manifest,proof,records):
    if (manifest['schema_version']!=1 or proof['schema_version']!=1
        or manifest['client_sha256']!=CLIENT_SHA or proof['client_sha256']!=CLIENT_SHA
        or manifest['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
        or manifest['predicate_rva']!='0x868240' or manifest['rightclick_rva']!='0x220ebd0'
        or manifest['ordinary_town_only'] is not True or manifest['authorizes_equipment_move'] is not False
        or proof['probe_version']!=2 or proof['applied_to_game'] is not False or len(proof['rows'])!=manifest['count'] or proof['count']!=manifest['count']):
        raise ValueError('Wear eligibility evidence scope')
    classes=classes_and_slots()[0];result={};total=0
    base_classes={v['family']:k for k,v in classes.items() if v['route']==0 and v['stage']==0}
    for row in proof['rows']:
        t=row['template'];raw=records.get(t)
        if t in result or raw is None or len(raw)!=232 or hashlib.sha256(raw).hexdigest()!=row['record_sha256']:raise ValueError('Wear template identity')
        flags4=int.from_bytes(raw[4:8],'little');flags8=int.from_bytes(raw[8:12],'little');mode=(flags4>>12)&15
        if (row['flags4'],row['flags8'],row['mode'],row['level'],row['unit_type'],row['unit_class'])!=(flags4,flags8,mode,raw[0xd1],raw[0xd2],raw[0xd3]):raise ValueError('Wear template fields')
        if mode not in (1,2,3) or flags4&1:raise ValueError('Unverified restriction mode')
        if mode==1:
            if set(row['models'])!={str(v) for v in range(1,16)} or not isinstance(row['generic_model'],str):raise ValueError('Common armor models missing')
            if any(not isinstance(v,str) or len(v)>1024 for v in [row['generic_model'],*row['models'].values()]):raise ValueError('Model name bound')
        elif row['generic_model'] is not None or row['models']:raise ValueError('Unexpected model evidence')
        matching=row['unit_class'] if row['unit_class'] in classes else base_classes[row['unit_type'] or 1]
        if matching not in classes:raise ValueError('Unknown matching class')
        other=2 if classes[matching]['family']==1 else 1
        tested_classes=set(base_classes.values()) if mode==1 else {matching,base_classes[classes[matching]['family']],other}
        tested_levels={max(0,row['level']-1),row['level'],99}
        expected={(c,l) for c in tested_classes for l in tested_levels};seen=set()
        for c,l,actual in row['cases']:
            if (c,l) not in expected or (c,l) in seen or type(actual) is not int or actual!=int(_allowed(row,c,l)):raise ValueError('Wear native case mismatch')
            seen.add((c,l));total+=1
        if seen!=expected:raise ValueError('Wear boundary cases missing')
        result[t]=MappingProxyType({**row,'models':MappingProxyType(dict(row['models'])),'cases':tuple(tuple(c) for c in row['cases'])})
    if total!=proof['case_count'] or total!=manifest['case_count']:raise ValueError('Wear native case count')
    return MappingProxyType(result)


@functools.lru_cache(maxsize=1)
def catalog():
    manifest=json.loads((PROJECT_ROOT/'els_server/data/equipment_eligibility.manifest.json').read_text())
    raw=(PROJECT_ROOT/manifest['proof']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['proof_sha256']:raise ValueError('Wear native proof digest')
    normal=definitions()
    with client_data().connect() as db:records={t:r for t,r in db.execute('SELECT id,record FROM items') if t in normal}
    result=dict(validate_proof(manifest,json.loads(raw),records))
    from els_server.domain.early_weapon_equipment import wear_proof
    extra_manifest,extra_proof=wear_proof()
    extra=validate_proof(extra_manifest,extra_proof,records)
    if set(result)&set(extra):raise ValueError('Duplicate early weapon wear evidence')
    result=MappingProxyType({**result,**extra})
    if set(result)!=set(normal):raise ValueError('Wear catalog coverage')
    return result


def inspect_eligibility(template,unit_class,level):
    if type(template) is not int or template not in catalog():raise ValueError('Unverified equipment')
    if type(unit_class) is not int or unit_class not in classes_and_slots()[0]:raise ValueError('Unknown character class')
    if type(level) is not int or not 1<=level<=99:raise ValueError('Character level')
    row=catalog()[template];routine=_allowed(row,unit_class,level)
    # Right-click 2213F33 independently applies D3 when nonzero, regardless of mode.
    extra_class=class_matches(unit_class,row['unit_class'])
    blocked=bool(row['flags4']&0x10)
    return dict(template=template,unit_class=unit_class,level=level,required_level=row['level'],
                restriction_mode=row['mode'],permitted_use_flags=bool(row['flags4']&0xf00),
                native_template_predicate=routine,additional_class_matches=extra_class,
                template_blocked=blocked,template_requirements_met=routine and extra_class and not blocked,
                authorizes_equipment_move=False,
                pending=['Owned instance usability and dynamic restrictions','Wear transaction and native combat refresh'])
