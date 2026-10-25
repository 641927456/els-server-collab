"""Native default normal equipment's template bonuses and derived stat fields.

The two retained vector fields remain unnamed. Enhancement/mode arguments are
calculation inputs only, not permission to grant enhanced inventory instances.
"""
import functools,hashlib,json,math,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.character_stats import f32,equipment_attributes
from els_server.domain.normal_equipment import definitions


@functools.lru_cache(maxsize=1)
def catalog():
    folder=PROJECT_ROOT/'els_server/data/client'
    manifest=json.loads((folder/'instance_stats.manifest.json').read_text())
    raw=(folder/'instance_stats.json').read_bytes();data=json.loads(raw)
    if (manifest['schema_version']!=1 or data['schema_version']!=1
        or hashlib.sha256(raw).hexdigest()!=manifest['sha256']
        or manifest['client_sha256']!=data['client_sha256'] or data['client_sha256']!=CLIENT_SHA
        or data['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
        or manifest['source_catalog_sha256']!=data['source_catalog_sha256']
        or data['normal_template_count']!=len(definitions()) or not data['default_additional_vector_zero']):
        raise ValueError('Instance stat evidence identity')
    return data


def normal_instance_attributes(template,character,*,enhancement=0,mode=0):
    if template not in definitions():raise ValueError('Outside verified normal instance scope')
    if type(enhancement) is not int or not 0<=enhancement<=20:raise ValueError('Enhancement calculation bound')
    if type(mode) is not int or mode not in (0,1):raise ValueError('Native instance mode')
    data=catalog();bonus=[0.]*6
    for effect_id in data['template_effects'].get(str(template),[]):
        effect=data['effects'][str(effect_id)]
        scale=enhancement if effect['scale_flag']==1 and effect['scale_kind']==10 else 1
        bonus=[f32(v+f32(x*scale)) for v,x in zip(bonus,effect['values'])]
    values=list(equipment_attributes(template,character,additional_bonus=bonus,owner_level=template in data['owner_level_templates']))
    ratio=struct.unpack_from('<f',client_data().item(template)['record'],0x2c)[0]
    if not math.isfinite(ratio):raise ValueError('Invalid native stat ratio')
    values[3]=f32(f32(values[1]*ratio)*data['ratio_scale'])
    values[4]=f32(f32(values[2]*ratio)*data['ratio_scale'])
    effective=7 if template in data['fixed_seven_templates'] else enhancement
    multiplier=data['enhancement_factors'][mode][effective]
    return tuple(f32(v*multiplier) for v in values)
