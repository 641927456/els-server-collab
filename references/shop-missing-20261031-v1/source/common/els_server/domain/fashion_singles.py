"""Finite standalone fashion offers backed by native records and decoder proof."""
import functools,hashlib,json,struct
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

POSITIONS={6:(11,'DEFENCE_HAIR_FASHION'),8:(12,'DEFENCE_BODY_FASHION'),
           9:(13,'DEFENCE_LEG_FASHION'),10:(14,'DEFENCE_HAND_FASHION'),
           11:(15,'DEFENCE_FOOT_FASHION'),2:(16,'WEAPON_HAND_FASHION'),
           38:(17,'ONEPIECE_FASHION')}


@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.storage.characters import BASE_CLASSES
    from els_server.domain.acquisition_policy import has_legacy_marker
    base=PROJECT_ROOT/'els_server/data'
    manifest=json.loads((base/'fashion_singles.manifest.json').read_text(encoding='utf8'))
    content=(base/'fashion_singles.json').read_bytes();data=json.loads(content)
    def verified(path,expected):
        raw=(PROJECT_ROOT/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Standalone fashion source changed')
        return json.loads(raw)
    if (manifest['schema_version']!=1 or manifest['client_sha256']!=CLIENT_SHA or data['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(content).hexdigest()!=manifest['catalog_sha256']):raise ValueError('Standalone fashion catalog identity')
    proof=verified(manifest['proof'],manifest['proof_sha256'])
    exclusion=verified(manifest['exclusions'],manifest['exclusions_sha256'])
    if (proof.get('ok') is not True or proof['client_sha256']!=CLIENT_SHA or proof.get('live_process') is not False
        or exclusion['client_sha256']!=CLIENT_SHA or exclusion['sources']!=manifest['sources']):raise ValueError('Standalone fashion proof identity')
    for source in manifest['sources']:verified(source['path'],source['sha256'])
    excluded=set().union(*(set(exclusion[k]) for k in ('package_members','package_parents','ice_templates','ice_machines')))
    rows=data['offers'];ids=[r['template'] for r in rows];evidence={r['template']:r for r in proof['rows']}
    if (len(ids)!=manifest['count'] or manifest['count']!=1250 or len(set(ids))!=len(ids)
        or sorted(ids)!=manifest['templates'] or set(ids)!=set(evidence) or proof['count']!=len(evidence)
        or set(ids)&excluded):raise ValueError('Standalone fashion finite scope/exclusions')
    client=client_data();slots=client.resource('Enum.lua')['NOW_EQIP_SLOT_ID']
    if client.manifest['catalog_sha256']!=manifest['catalog_source_sha256']:raise ValueError('Standalone fashion item source')
    for row in rows:
        t=row['template'];item=client.item(t);raw=bytes.fromhex(row['record_hex']);p=evidence[t]
        position=row['resource_position_byte'];category,suffix=POSITIONS[position]
        minor=bool(raw[8]&4);name=('NESI_MINORUNIT_' if minor else 'NESI_')+suffix
        if (len(raw)!=232 or raw!=item['record'] or struct.unpack_from('<I',raw)[0]!=t or item['name']!=row['name']
            or item['item_type'] not in (1,2) or item['flags4']&33!=1 or item['flags4']&0xffff0000!=0x00400000
            or item['equip_position']!=position or raw[210]!=row['role'] or row['role'] not in range(1,16)
            or raw[211] not in (0,BASE_CLASSES[row['role']]) or minor!=row['minor'] or minor and row['role']!=10
            or has_legacy_marker(row['name']) or row['category']!=category or row['sku']!=1200000000+t
            or not 0<row['sku']<2**31 or row['price']!=50 or row['quantity']!=1 or row['max_stack']!=1
            or row['metadata']!=item['metadata'] or row['metadata']!=raw[7]&15
            or row['group']!=(27 if item['flags8']&256 else 7) or row['equipment_slot']!=slots[name]):
            raise ValueError('Standalone fashion native record/category/slot')
        if not (p['ok'] is True and p['consumed']==304 and p['fields_match'] is True and p['vectors_empty'] is True
                and p['native_template_id']==t and p['native_group']==row['group']
                and p['record_sha256']==hashlib.sha256(raw).hexdigest() and p['equipment_slot']==slots[name]
                and p['enum_slot']==name and p['applied_to_game'] is False and p['no_reward_persistence'] is True):
            raise ValueError('Standalone fashion native decoder coverage')
    return tuple(rows)


def offers(unit_type=None):
    return tuple({k:r[k] for k in ('sku','template','name','category','price','quantity')}
                 for r in definitions() if unit_type is None or r['role']==unit_type)


@functools.lru_cache(maxsize=1)
def onepiece_templates():
    """Owner-authorized complete onepiece storefront, not generic new sources."""
    return frozenset(r['template'] for r in definitions() if r['category']==17)
