"""Current/endurance limits from the pinned normal-equipment template.

Missing historical fields remain zero. New local grants initialize to the
client-defined maximum; this is an explicit grant policy, not retail drop data.
"""
import functools,hashlib,json,struct
from els_server.domain.normal_equipment import definitions
from els_server.game_data import client_data,CLIENT_SHA
from els_server.paths import PROJECT_ROOT

from els_server.domain.fishing_equipment import RODS
FISHING_DURABILITY_TEMPLATES = RODS | {135929, 135930, 135931, 135932}
# These owned templates historically omitted the durability row on creation.
# The bag and source hash distinguish them from worn gear and other components.
LEGACY_INITIAL_DURABILITY = {
    135995: (21, 'e955937c4dfb0e8ab7cafb65cb848929414c19980c5a3d7871f0f2218d44bdb6'),
    118332: (1, 'cf9dd9b06b629453c095f98298c9b339c3a8798ddeda2c06899a5cdbe73fe418'),
    118333: (1, 'd8b5d5e1b7d9293845a80cd09bb60ce62025da4b19a289f6dfc1fedd08158024'),
    118334: (1, '0bd938c0a49ad25cd4b00b005a61a84f537775c712de06847768e9028706b269'),
    118335: (1, 'ff8fd0a33ced986551d0175d9e52881cdd9d70a98e4d31d02dd5980c2275ff59'),
}


@functools.lru_cache(maxsize=1)
def evidence():
    m=json.loads((PROJECT_ROOT/'els_server/data/equipment_durability.manifest.json').read_text())
    raw=(PROJECT_ROOT/m['proof']).read_bytes();p=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=m['proof_sha256'] or p['client_sha256']!=CLIENT_SHA
        or m['client_sha256']!=CLIENT_SHA or (m['wire_offset'],m['wire_type'],m['object_offset'],m['template_maximum_offset'])!=(9,'signed_i16',16,200)
        or m['legacy_missing_value']!=0 or m['grant_initialization']!='local_policy_client_template_maximum'
        or p['count']!=80 or len(p['rows'])!=80):raise ValueError('Durability evidence identity')
    expected={(t,v,s) for t in (100,30154,30224,30388,119241) for v in (-1,0,1,1999,2000,9999,10000,32767) for s in ((),(1,0,0,0))}
    seen=set()
    for r in p['rows']:
        key=(r['template'],r['durability'],tuple(r['expected']));record=client_data().item(r['template'])['record']
        if key not in expected or key in seen:raise ValueError('Durability case coverage')
        seen.add(key)
        if (hashlib.sha256(record).hexdigest()!=r['record_sha256'] or r['maximum']!=struct.unpack_from('<h',record,0xc8)[0]
            or r['ok']!=1 or r['fields_match'] is not True or r['other_vectors_empty'] is not True
            or r['consumed']!=r['size'] or r['size']!=304+4*len(r['expected']) or r['actual']!=r['expected']
            or r['object_slots']!=r['expected']+[0]*(4-len(r['expected'])) or r['metadata']!=1 or r['native_group']!=1 or r['count']!=1
            or r['usable']!=int(r['durability']>0) or r['applied_to_game'] is not False):raise ValueError('Native durability witness mismatch')
    return m


def maximum(template):
    evidence()
    record=client_data().item(template)['record']
    if template in LEGACY_INITIAL_DURABILITY:
        if hashlib.sha256(record).hexdigest() != LEGACY_INITIAL_DURABILITY[template][1]:
            raise ValueError('Legacy initial durability definition')
    elif template in FISHING_DURABILITY_TEMPLATES:
        from els_server.domain.fishing_equipment import definition
        definition(template)
    elif template not in definitions():raise ValueError('Unverified durability equipment')
    value=struct.unpack_from('<h',record,0xc8)[0]
    if not 0<value<=32767:raise ValueError('Native durability maximum')
    return value


def validate(template,value):
    if type(value) is not int or not 0<=value<=maximum(template):raise ValueError('Equipment durability out of range')
    return value
