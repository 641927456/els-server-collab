"""Normal bag equipment admitted by per-template native codec/eligibility proof.

Registration does not grant items or enable wearing them. Special flags,
random enchant rolls and event-dependent prices are outside this catalog.
"""
import functools,hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


def validate_proof(manifest,proof,records):
    if (manifest['schema_version']!=1 or proof['schema_version']!=1
        or manifest['client_sha256']!=CLIENT_SHA or proof['client_sha256']!=CLIENT_SHA
        or manifest['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
        or proof['source_catalog_sha256']!=manifest['source_catalog_sha256']
        or proof['applied_to_game'] is not False or proof['count']!=len(proof['rows'])
        or manifest['policy']!={'bag_group':1,'metadata':1,'max_stack':1,'normal_flags_mask':161}):
        raise ValueError('Normal equipment native proof identity')
    result={};seen=set()
    for row in proof['rows']:
        template=row['template']
        if template in seen:raise ValueError('Duplicate normal equipment witness')
        seen.add(template)
        if row['accepted'] is not True:continue
        raw=records.get(template)
        if raw is None or len(raw)!=232 or hashlib.sha256(raw).hexdigest()!=row['record_sha256']:raise ValueError('Normal equipment record identity')
        flags4=int.from_bytes(raw[4:8],'little');flags8=int.from_bytes(raw[8:12],'little')
        kind=(flags8>>3)&31;capacity=raw[0xd8];metadata=raw[7]&15
        source=row['source']
        expected=dict(template=template,flags4=flags4,flags8=flags8,metadata=metadata,capacity=capacity,
                      level=raw[0xd1],level_override=raw[0xd9],record_sha256=row['record_sha256'])
        if (source!=expected or kind not in (1,2) or flags4&0xa1 or metadata!=1 or not 1<=capacity<=4
            or row['metadata']!=1 or row['group']!=1 or row['capacity']!=capacity or len(row['cases'])!=2):
            raise ValueError('Normal equipment definition constraints')
        for case,populated in zip(row['cases'],(False,True)):
            size=320 if populated else 304;slots=[1]*capacity+[0]*(4-capacity) if populated else [0]*4
            if (case['size']!=size or case['consumed']!=size or case['slots']!=slots
                or case['restriction']!=0 or case['level_value']<0):raise ValueError('Normal equipment private item mismatch')
        rules=client_data().enchanting
        for count in range(capacity):
            rules.normal_ed_cost(count,kind==1,raw[0xd9] or raw[0xd1],(flags4>>20)&15)
            rules.normal_material_cost(kind==1,count,raw[0xd9] or raw[0xd1],(flags4>>20)&15)
        result[template]=MappingProxyType(dict(template=template,metadata=1,group=1,max_stack=1))
    if len(result)!=manifest['count'] or len(result)!=proof['accepted_count']:raise ValueError('Normal equipment proof coverage')
    return MappingProxyType(result)


@functools.lru_cache(maxsize=1)
def definitions():
    manifest=json.loads((PROJECT_ROOT/'els_server/data/normal_equipment.manifest.json').read_text(encoding='utf8'))
    raw=(PROJECT_ROOT/manifest['proof']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest['proof_sha256']:raise ValueError('Normal equipment proof digest')
    with client_data().connect() as db:
        records=dict(db.execute('SELECT id,record FROM items WHERE item_type IN (1,2)'))
    result=dict(validate_proof(manifest,json.loads(raw),records))
    from els_server.domain.early_weapon_equipment import definitions as appendix
    extra=appendix()
    if set(result)&set(extra):raise ValueError('Duplicate early weapon appendix')
    return MappingProxyType({**result,**extra})
