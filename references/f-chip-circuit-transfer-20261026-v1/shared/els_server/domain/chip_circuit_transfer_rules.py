"""Exact original source/target membership; approved zero-cost server policy."""
from pathlib import Path
import functools
import hashlib
import json
from els_server.game_data import client_data, CLIENT_SHA

DATA_SHA = 'b269782975f2ef76960bec9a66f9c24b035961b68000e361f641ef10fbc93602'


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/chip_circuit_transfer.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:
        raise ValueError('Chip/circuit transfer policy identity')
    p=json.loads(raw);data=client_data()
    if (p['schema']!=1 or p['client_sha256']!=CLIENT_SHA
        or p['catalog_sha256']!=data.manifest['catalog_sha256']
        or (p['town'],p['scene'],p['house'],p['npc'],p['button'])!=(1012,1214,40327,10501,63)
        or p['groups']!=[27,28] or p['source_must_have_both']is not True
        or p['additional_ed']!=0 or p['additional_materials']!=[]
        or p['fee_is_explicit_local_rule']is not True or len(p['records'])!=120):
        raise ValueError('Finite F chip/circuit transfer policy')
    pairs=frozenset(tuple(row)for row in p['pairs'])
    if (len(p['pairs'])!=900 or len(pairs)!=900
        or len({a for a,b in pairs})!=60 or len({b for a,b in pairs})!=60
        or {a for a,b in pairs}&{b for a,b in pairs}):
        raise ValueError('Original chip/circuit transfer membership')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    for key,row in p['records'].items():
        template=int(key);item=data.item(template)
        if (row['template']!=template or item['item_type']!=2 or item['equip_position']!=row['part']
            or item['metadata']!=1 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or (VERIFIED_TEMPLATES.get(template),TEMPLATE_BAG_GROUPS.get(template),TEMPLATE_MAX_STACKS.get(template))!=(1,1,1)):
            raise ValueError('Original registered transfer armor record')
    if any(p['records'][str(a)]['part']!=p['records'][str(b)]['part']for a,b in pairs):
        raise ValueError('Original transfer same equipment slot')
    return p,pairs


def transform(source,target):
    p,pairs=catalog()
    if (source['template'],target['template'])not in pairs:
        raise ValueError('Unadmitted original transfer pair')
    from els_server.domain.equipment_chip_rules import armor_options
    from els_server.domain.equipment_circuit_rules import validate_grid
    a=source.get('option_groups',{});b=target.get('option_groups',{})
    if '27'not in a or '28'not in a:
        raise ValueError('Source must have both original chip and circuit')
    chip=armor_options(source['template'],a['27'])
    circuit=validate_grid(source['template'],a['28'])
    if not any(circuit):
        raise ValueError('Source circuit must contain an installed circuit')
    armor_options(target['template'],chip);validate_grid(target['template'],circuit)
    return ({k:v for k,v in a.items()if k not in('27','28')},
            {**b,'27':list(chip),'28':list(circuit)})
