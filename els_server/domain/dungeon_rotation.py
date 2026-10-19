"""Native CCA/CCC/CCD Silver Mirror Valley selection, explicit local policy."""
import functools,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.protocol.protocol_codec import Event

@functools.lru_cache(maxsize=1)
def rotation():
    from els_server.domain.region_quests import region_catalog
    from els_server.domain.dungeon_routes import route_catalog
    row=json.loads((PROJECT_ROOT/'config/dungeon_rotation_local.json').read_text(encoding='utf8'))
    if row['schema_version']!=1 or row['provenance']!='local_policy':raise ValueError('Tower rotation provenance')
    if (len(row['normal'])!=3 or len(set(row['normal']))!=3 or len(row['buffs'])!=2
        or any(type(v) is not int or not 0<=v<2**31 for v in [row['rotation'],row['boss_count'],row['story'],*row['normal'],*row['buffs']])):raise ValueError('Tower rotation bounds')
    if row['boss_count']!=0 or row['buffs']!=[0,0]:raise ValueError('Unverified tower bonus/buff policy')
    data=region_catalog().data
    for identity in [*row['normal'],row['story']]:
        if 10042 not in data['dungeons'].get(str(identity),[]) or not route_catalog().supports(identity):raise ValueError('Tower encounter unavailable')
    return row

def tower_encounter(identity):
    from els_server.domain.region_quests import region_catalog
    return 10042 in region_catalog().data['dungeons'].get(str(identity),[])

def selected(identity):
    row=rotation();return identity in [*row['normal'],row['story']]

def body():
    # 2BE37D0/DAEB80: two i32, count=3 + fixed i32[3], one i32,
    # count=2 + fixed i32[2]. Array extents are present on the wire.
    r=rotation()
    return struct.pack('>10i',r['rotation'],r['boss_count'],3,*r['normal'],r['story'],2,*r['buffs'])

def notification():return Event(0x201,kind=0xcca,payload=body())

def handle(s,event):
    if event.event_id!=0x202 or event.kind!=0xccc:return None
    valid=(s.role=='game' and s.phase in ('town_ready','dungeon_active') and event.payload==b''
        and event.performers==(0,) and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0)
    return [Event(0x201,kind=0xccd,payload=struct.pack('>i',0 if valid else -1)+body())]
