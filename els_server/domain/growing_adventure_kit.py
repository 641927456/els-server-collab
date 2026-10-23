"""One normal story full-set box; original gear calculations remain native."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA
BOX=168889
SHA='5bb34b7d0c33f135886a74533e23e32732e9f674cf94311656926eeffeb745ae'

@functools.lru_cache(maxsize=1)
def source():
    raw=(Path(__file__).resolve().parents[1]/'data/growing_adventure_kit.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Growing kit source identity')
    d=json.loads(raw);client=client_data()
    if (d['schema_version'],d['template'],d['client_sha256'],d['source_catalog_sha256'],d['use_condition'],d['selection_count'],d['extra_ED'],d['extra_key'],d['output_deadline'])!=(1,BOX,CLIENT_SHA,client.manifest['catalog_sha256'],2,0,0,0,None):
        raise ValueError('Growing kit fixed source scope')
    item=client.item(BOX)
    if item['name']!=d['source_name']or hashlib.sha256(item['record']).hexdigest()!=d['source_record_sha256']:raise ValueError('Growing box source record')
    from els_server.domain.equipment_requirements import catalog
    from els_server.domain.normal_equipment import definitions
    classes=catalog()[0];normal=definitions();records={r['template']:r for r in d['records']}
    if len(records)!=19 or len(d['kits'])!=15 or {r['current_family']for r in d['kits']}!=set(range(1,16)):raise ValueError('Growing kit family scope')
    for t,row in records.items():
        item=client.item(t)
        if (t not in normal or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
                or (item['name'],item['item_type'],item['equip_position'],item['record'][0xd3])!=(row['name'],row['item_type'],row['equip_position'],row['required_class'])):
            raise ValueError('Growing kit exact equipment source')
    for kit in d['kits']:
        base=kit['required_base_class'];weapon=records[kit['weapon_template']];armor=[records[t]for t in kit['ordinary_armor_templates']]
        if (base not in classes or classes[base]['family']!=kit['current_family']or weapon['required_class']!=base or weapon['item_type']!=1
                or sorted(r['equip_position']for r in armor)!=[8,9,10,11]or any(r['required_class']or r['item_type']!=2 for r in armor)
                or kit['proposed_quantities']!=[1]*5 or kit['minor_group']not in(None,kit['source_itemgroup'])):
            raise ValueError('Growing kit family/part identity')
    return d

def outputs_for(unit_class):
    from els_server.domain.equipment_requirements import catalog,class_matches
    classes=catalog()[0]
    if type(unit_class)is not int or unit_class not in classes:raise ValueError('Growing kit owner class')
    matches=[r for r in source()['kits']if r['current_family']==classes[unit_class]['family']and class_matches(unit_class,r['required_base_class'])]
    if len(matches)!=1:raise ValueError('Growing kit owner family')
    kit=matches[0]
    return tuple(dict(template=t,quantity=1)for t in(kit['weapon_template'],*kit['ordinary_armor_templates']))

def entry():
    source()
    return dict(template=BOX,selection_count=0,entries=(),growing_adventure_kit=True)
