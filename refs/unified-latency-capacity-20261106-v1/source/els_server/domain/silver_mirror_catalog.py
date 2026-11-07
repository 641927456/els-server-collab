"""Pinned client inputs and explicitly labelled Silver Mirror local economy."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

INVITATIONS=(722538,722539,722540,722541)
T_CIRCUITS=frozenset(range(118590,118638))

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/silver_mirror.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='4f690a6ee28c8ea4675ae39d34b154107e1e03bfd7aad0cae08771c65ccccb41':raise ValueError('Silver Mirror policy fingerprint')
    data=json.loads(raw)
    if data['schema']!=1 or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Silver Mirror pinned client')
    if len(data['buffs'])!=30 or set(data['t_circuits'])!=T_CIRCUITS:raise ValueError('Silver Mirror finite source scope')
    for key,row in data['items'].items():
        d=client_data().item(int(key))
        if row['template']!=int(key)or(row['metadata'],row['item_type'],row['record_sha256'])!=(d['metadata'],d['item_type'],hashlib.sha256(d['record']).hexdigest()):raise ValueError('Silver Mirror item record')
    return data

def definitions():
    from els_server.domain.equipment_circuit_rules import material
    rows=[]
    for t in T_CIRCUITS:
        c=material(t)
        if c is None or(c['metadata'],c['registered_group'],c['max_stack'])!=(1,1,1):raise ValueError('Silver Mirror inherited T instance contract')
    for t in INVITATIONS:
        r=catalog()['items'][str(t)]
        rows.append(dict(template=t,metadata=r['metadata'],group=4,max_stack=999))
    return rows

def buff_pool(dungeon):
    # Existing source families are retained; the undisclosed sampling weights
    # and common/family union are explicitly recorded as local selection policy.
    family={35720:'UNDERGROUND',35730:'RESIDENCE',35740:'ABYSS',35750:'GOLDCASTLE'}.get(dungeon)
    if family is None:raise ValueError('Silver Mirror stage has no buff offer')
    return sorted(int(k)for k,r in catalog()['buffs'].items()if '_COMMON_'in r['name']or('_'+family+'_')in r['name'])

def world_row(owner,row):
    import struct
    r=catalog()['buffs'].get(str(row['template']))
    if not r or row['owner']!=owner or not 1<=row['start']<row['end']<2**31:raise ValueError('Silver Mirror owned world effect')
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',r['template'],0,owner,0.,1,0,0.,False,r['factor'],1.,False,-1,0,0,row['start'],row['end'])
