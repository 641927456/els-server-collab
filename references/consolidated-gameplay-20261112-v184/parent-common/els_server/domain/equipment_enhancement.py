"""The verified signed-byte instance enhancement field, limited to known factors."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA
from els_server.domain.normal_equipment import definitions


@functools.lru_cache(maxsize=1)
def evidence():
    m=json.loads((PROJECT_ROOT/'els_server/data/equipment_enhancement.manifest.json').read_text())
    raw=(PROJECT_ROOT/m['proof']).read_bytes();proof=json.loads(raw)
    if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or proof['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=m['proof_sha256']
        or (m['wire_offset'],m['dto_offset'],m['object_offset'],m['wire_type'])!=(12,12,24,'signed_i8')
        or (m['supported_min'],m['supported_max'],m['absent_value'])!=(0,20,0)
        or proof['complete']['cases']!=6200 or len(proof['rows'])!=124):raise ValueError('Enhancement codec evidence')
    cases={(v,x) for v in [*range(21),-128,-1,21,127] for x in (False,True)}
    seen=set()
    for row in proof['rows']:
        if row['template'] not in definitions() or row['template'] in seen:raise ValueError('Enhancement template witness')
        seen.add(row['template'])
        if {(r['value'],r['extended']) for r in row['cases']}!=cases or len(row['cases'])!=50:raise ValueError('Enhancement codec case coverage')
        for r in row['cases']:
            if (r['actual']!=r['value'] or r['consumed']!=r['size'] or r['size']!=(358 if r['extended'] else 304)
                or r['slots']!=([1,0,0,0] if r['extended'] else [0]*4)
                or r['date']!=('2026-12-31 23:59:59' if r['extended'] else '')
                or r['durability']!=10000 or r['count']!=1):raise ValueError('Enhancement native field witness')
    return m


def validate(template,value):
    evidence()
    # Original 198B8D0 rejects negative enhancement as broken; 23E94C0 and
    # 23EF270 display its absolute level. Durability is a separate field.
    if template not in definitions() or type(value) is not int or not (0<=value<=20 or -13<=value<=-8):raise ValueError('Unsupported equipment enhancement')
    return value
