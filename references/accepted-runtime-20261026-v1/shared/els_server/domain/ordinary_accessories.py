"""Current ordinary accessory slots and owned-instance wear prerequisites.

This is server-side compatibility for saved items. Registration does not add
loot/shop/reward sources or reconstruct native effect/stat calculations.
"""
import functools,hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def definitions():
    base=PROJECT_ROOT/'els_server/data'
    m=json.loads((base/'ordinary_accessories.manifest.json').read_text('utf-8'))
    raw=(PROJECT_ROOT/m['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=m['sha256']:raise ValueError('Accessory catalog digest')
    p=json.loads(raw);c=client_data()
    if (p['schema']!=1 or p['client_sha256']!=CLIENT_SHA or p['source_catalog_sha256']!=c.manifest['catalog_sha256']
        or p['enum_sha256']!=next(s['sha256'] for s in c.manifest['sources'] if s['name']=='Enum.lua')):raise ValueError('Accessory catalog identity')
    e=c.resource('Enum.lua');ep=e['EQIP_POSITION'];ns=e['NOW_EQIP_SLOT_ID']
    slots={ep['EP_AC_'+s]:(ns['NESI_AC_'+s],ns['NESI_MINORUNIT_AC_'+s]) for s in ('FACE1','FACE2','FACE3','BODY','LEG','ARM','RING','NECKLESS','WEAPON','MINIME','EARRING')}
    if {int(k):tuple(v) for k,v in p['slot_pairs'].items()}!=slots:raise ValueError('Accessory source slots')
    with c.connect() as db:records=dict(db.execute('SELECT id,record FROM items WHERE item_type=3'))
    result={}
    for r in p['rows']:
        t=r['template'];source=records.get(t);flags=int.from_bytes(source[4:8],'little') if source else 0
        if (t in result or not source or len(source)!=232 or hashlib.sha256(source).hexdigest()!=r['record_sha256']
            or flags&0xa1 or (flags>>12)&15 not in (1,2,3) or source[7]&15 or source[0xd5] not in slots
            or tuple(r['slots'])!=slots[source[0xd5]] or (r['metadata'],r['group'],r['max_stack'])!=(0,2,1)
            or type(r['compatibility_only']) is not bool or type(r['restricted']) is not bool):raise ValueError('Accessory source record')
        # The same native companion bit already selects minor fashion slots.
        # Companion-only accessories must not become wearable on Lu's side.
        main=(r['slots'][0],);minor=(r['slots'][1],)
        # A ring template keeps EP_AC_RING in both ordinary ring slots. The
        # second slot is a destination, not a separate EP_AC_RING2 template.
        if source[0xd5]==ep['EP_AC_RING']:
            main+=(ns['NESI_AC_RING2'],);minor+=(ns['NESI_MINORUNIT_AC_RING2'],)
        if source[8]&4:main=()
        result[t]=MappingProxyType({**r,'slots':main+minor,'main_slots':main,'companion_only':bool(source[8]&4)})
    if len(result)!=m['count']:raise ValueError('Accessory catalog coverage')
    return MappingProxyType(result)

def accepts_equipped(item):
    r=definitions().get(item.get('template'))
    return bool(r and item['metadata']==0 and item['count']==1 and item['group']==9 and item['slot'] in r['slots'])

def require_wearable(item,character):
    if not accepts_equipped(item):raise ValueError('Accessory destination slot')
    r=definitions()[item['template']]
    if r['restricted']:raise ValueError('Unsupported special accessory permission')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.equipment_requirements import class_matches
    # A UID lock protects destructive/transfer operations; wearing retains it.
    require_current(item)
    c=client_data();raw=c.item(item['template'])['record'];family=c.unit(character['unit_class'])['unitType']
    if family!=character['unit_type'] or type(character['level']) is not int or not 1<=character['level']<=99:raise ValueError('Accessory owner identity')
    if r['companion_only'] and family!=10:raise ValueError('Companion accessory belongs to LuCiel')
    if family!=10 and item['slot'] not in r['main_slots']:raise ValueError('Minor accessory belongs to LuCiel')
    flags=int.from_bytes(raw[4:8],'little');mode=(flags>>12)&15
    # 868240 mode1 only checks armor models for type2; accessories are type3.
    allowed=mode==1 or mode==2 and family==raw[0xd2] or mode==3 and class_matches(character['unit_class'],raw[0xd3])
    if not flags&0xf00 or flags&0x10 or character['level']<raw[0xd1] or not allowed or not class_matches(character['unit_class'],raw[0xd3]):raise ValueError('Accessory template requirements')
    optional=set()
    if item['template']==30603:
        from els_server.domain.accessory_identification import validate as validate_identification
        values=item.get('option_groups',{}).get('1',[])
        # An old worn instance with no initialized state remains readable. New
        # equips from bag2 must have the committed original two-line result.
        if item.get('identified')is not True or not values:raise ValueError('Accessory must be identified before wearing')
        validate_identification(item['template'],values)
        optional={'identified','option_groups'}
    if set(item)-({'uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_used','appearance_template','wardrobe_hanger','dye_colors','appearance_colors'}|optional):raise ValueError('Unsupported accessory instance data')
