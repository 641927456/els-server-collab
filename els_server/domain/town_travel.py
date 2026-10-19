"""Source-bound ordinary-town admission and economic price, no native UI work."""
import functools,hashlib,json,struct
from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT
from els_server.domain.seal_quests import sequence

@functools.lru_cache(maxsize=1)
def catalog():
    root=PROJECT_ROOT/'els_server/data';raw=(root/'town_travel.json').read_bytes()
    m=json.loads((root/'town_travel.manifest.json').read_bytes());d=json.loads(raw)
    if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or d['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']
        or len(d['towns'])!=m['towns'] or len(d['map_groups'])!=m['map_groups']):raise ValueError('Town travel source identity')
    return d

def require_destination(destination,character,completed,dungeon_records):
    if type(destination) is not int or str(destination) not in catalog()['towns']:raise ValueError('Unsupported town destination')
    row=catalog()['towns'][str(destination)];r=row['requirement']
    types=sequence(r.get('EnableUnitType',{}))
    if types and character['unit_type'] not in types:raise ValueError('Town character type')
    minimum=max([r['REQUIRE_LEVEL']['MIN'],*[v['MIN_LEVEL'] for v in r.get('EnableUnitTypeLevel',{}).values() if v['UNIT_TYPE']==character['unit_type']]])
    if character['level']<minimum:raise ValueError('Town minimum level')
    if r.get('REQUIRE_COMPLETE_QUEST_ID') and r['REQUIRE_COMPLETE_QUEST_ID'] not in completed:raise ValueError('Town required quest')
    from els_server.domain.dungeon_routes import route_catalog
    # Reuse the admitted current-layout alias (e.g.30090 ->30092). Do not
    # resurrect an excluded normal difficulty or infer an ID +/-2 family.
    if any(route_catalog().entry_identity(i) not in dungeon_records for i in sequence(r.get('REQUIRE_DUNGEON',{}))):raise ValueError('Town required clear')
    return row

def price(source,destination,level):
    if any(type(i) is not int for i in (source,destination,level)) or not 1<=level<=99:raise ValueError('Town cost arguments')
    data=catalog();groups=data['map_groups']
    if source==destination or str(source) not in data['towns'] or str(destination) not in data['towns']:raise ValueError('Town cost source')
    a,b=groups.get(str(source),0),groups.get(str(destination),0)
    if not a or not b:raise ValueError('Unclassified town')
    distance=float(abs(a-b))
    # Literal instruction order: DIVVN, MULVV, SUBVN, MULVV, ADDVV, MULVV.
    cost=(float(level)/60.0)*(6000.0+(6000.0*0.6)*(distance-1.0))
    single=struct.unpack('<f',struct.pack('<f',cost))[0]
    result=int(single)  # Current7D4090 CVTPD2PS,312F3A4 CVTTSS2SI.
    if not 0<=result<2**31:raise ValueError('Town fee range')
    return result
