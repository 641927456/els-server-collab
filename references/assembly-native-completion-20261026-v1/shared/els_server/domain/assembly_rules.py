"""Finite current Type2 camps and owned uniforms; no client effect replacement."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

POLICY='assembly-native-20261026-v1'
DATA_SHA='0c2ded9d36217ba722fabf4c5c586c84bfa77b9e94fe961d3cd568a044b0311b'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/assembly.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Assembly policy identity')
    c=json.loads(raw)
    if(c['schema']!=1 or c['policy']!=POLICY or c['client_sha256']!=CLIENT_SHA
       or c['catalog_sha256']!=client_data().manifest['catalog_sha256']
       or set(c['towns'])!={'1009','1010','20013','1011','1012'}
       or len(c['uniforms'])!=64 or len({r['template']for r in c['uniforms']})!=64
       or c['new_item_sources']is not False):raise ValueError('Assembly finite client scope')
    n=c['native']
    if(n['spa_type'],n['buff_template'],n['factor'],n['world_flag'],n['store_flag'],
       n['duration_seconds'],n['stay_seconds'],n['price_ed'])!=(2,1433,1538,0,0,1800,360,500000):raise ValueError('Assembly native inputs')
    for r in c['uniforms']:
        d=client_data().item(r['template']);b=d['record']
        if(hashlib.sha256(b).hexdigest()!=r['record_sha256']or d['item_type']!=2 or d['equip_position']!=38
           or r['division']not in(120,121)or r['max_stack']!=1 or r['metadata']!=d['metadata']
           or r['group']!=(27 if d['flags8']&256 else 7)or r['role']!=b[210]or r['required_class']!=b[211]
           or r['minor']!=bool(b[8]&4)or r['equipment_slot']!=(36 if r['minor']else 35)
           or r['minor']and r['role']!=10):raise ValueError('Assembly native uniform')
    return c

def definitions():return tuple(catalog()['uniforms'])

def uniform(items,character,now):
    from els_server.domain.item_expiration import expired
    from els_server.domain.equipment_requirements import class_matches
    by_template={r['template']:r for r in definitions()};found=[]
    for i in items:
        r=by_template.get(i['template'])
        if not r or i['group']!=9 or i['slot']!=r['equipment_slot']or expired(i,now=now):continue
        if(i['count']!=1 or i['metadata']!=r['metadata']or character['unit_type']!=r['role']
           or not class_matches(character['unit_class'],r['required_class'])):raise ValueError('Assembly worn uniform identity')
        found.append(r['division'])
    return 121 if 121 in found else 120 if 120 in found else 0

def rate(division):
    if division not in(0,120,121):raise ValueError('Assembly uniform division')
    return 1. if not division else catalog()['native']['avatar_rates'][str(division)]

def quote(division):
    # Original2B521D0 multiplies the ED integer by the exact Lua double,
    # then truncates. The same explicit source rate also shortens waiting.
    r=rate(division)
    return int(500000*r),round(360*r)

def source_row(owner,state):
    return dict(owner=owner,template=1433,start=state['start'],end=state['end'],_assembly=True)

def wire_row(owner,row):
    if(row.get('_assembly')is not True or row['owner']!=owner or row['template']!=1433
       or any(type(row[k])is not int for k in('start','end'))or not 1<=row['start']<row['end']<2**31
       or row['end']-row['start']!=1800):raise ValueError('Assembly source-owned KBuffInfo')
    # Same original KBuffInfo reader and ctor defaults. Template/factor flags
    # remain native World0/Store0; no modified template or custom effect vector.
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',1433,0,owner,0.,1,0,0.,False,1538,1.,False,-1,0,0,row['start'],row['end'])
