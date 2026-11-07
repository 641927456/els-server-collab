"""Verified slot/class requirements; not yet a complete wear authorization."""
import functools,hashlib,json
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def catalog():
    m=json.loads((PROJECT_ROOT/'els_server/data/equipment_requirements.manifest.json').read_text())
    raw=(PROJECT_ROOT/m['proof']).read_bytes();p=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=m['proof_sha256'] or m['client_sha256']!=CLIENT_SHA
        or p['client_sha256']!=CLIENT_SHA or m['authorizes_equipment_moves'] is not False
        or p['slots']['applied_to_game'] is not False or p['classes']['applied_to_game'] is not False):raise ValueError('Equipment requirements proof')
    classes={r['id']:MappingProxyType(r) for r in p['classes']['rows']}
    with client_data().connect() as db:families=dict(db.execute('SELECT class_id,unit_type FROM units'))
    if (len(classes)!=m['class_count'] or len(classes)!=len(p['classes']['rows']) or set(classes)!=set(families)
        or p['classes']['cases']!=len(classes)**2 or m['pair_count']!=p['classes']['cases']
        or any(r['family']!=families[k] or r['route'] not in range(5) or r['stage'] not in range(4) for k,r in classes.items())):raise ValueError('Equipment class coverage')
    slots={r['position']:r['slot'] for r in p['slots']['rows'] if r['available'] and r['fashion']==0}
    if slots!={int(k):v for k,v in m['ordinary_positions'].items()} or set(slots)!={2,8,9,10,11}:raise ValueError('Ordinary slot coverage')
    for r in p['slots']['rows']:
        if r['available'] and (r['group']!=9 or r['native_position']!=r['position'] or r['native_fashion']!=r['fashion'] or r['alternate']!=0):raise ValueError('Equipment slot identity')
    return MappingProxyType(classes),MappingProxyType(slots)


def class_matches(unit_class,required_class):
    classes,_=catalog()
    if type(unit_class) is not int or unit_class not in classes or type(required_class) is not int:raise ValueError('Unknown equipment class')
    # The caller 2213F33 skips the predicate for a zero requirement.
    if required_class==0:return True
    if required_class not in classes:raise ValueError('Unverified required equipment class')
    a,b=classes[unit_class],classes[required_class]
    return a['family']==b['family'] and (b['route']==0 or a['route']==b['route']) and a['stage']>=b['stage']


def inspect_requirements(template,unit_class):
    from els_server.domain.normal_equipment import definitions
    if template not in definitions():raise ValueError('Outside verified normal inventory catalog')
    _,slots=catalog();item=client_data().item(template);required=item['record'][0xd3]
    return dict(template=template,name=item['name'],unit_class=unit_class,required_class=required,
                class_matches=class_matches(unit_class,required),equip_position=item['equip_position'],
                equipment_group=9,equipment_slot=slots[item['equip_position']],
                authorizes_equipment_move=False,
                pending=['This query reports template constraints only; the move handler also checks ownership, capacity and instance state',
                         'Dynamic account/event restrictions remain unsupported for seven templates',
                         'Durability loss and repair rules; historical missing values remain zero'])
