"""Original 219/21A and finite owned world snapshots for the pinned client."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.elixir_items import catalog

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=29:raise ValueError('Elixir request length')
    uid,additional,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or additional not in(0,1) or a or b or n or flag:raise ValueError('Elixir request fields')
    return uid,additional

def world_row(owner,row):
    if row.get('_silver'):
        from els_server.domain.silver_mirror_catalog import world_row as mirror_world_row
        return mirror_world_row(owner,row)
    rule=catalog()[row['template']]
    if (type(owner)is not int or not 1001<=owner<2**63 or row['owner']!=owner
        or type(row['start'])is not int or not 1<=row['start']<row['end']<2**31
        or row['end']-row['start']!=rule['period_seconds']):raise ValueError('Owned elixir world row')
    # DCF9C0 ctor defaults: opaque67=1, opaque6C=-1. No 3A7 row
    # defaults or custom effect/time vectors are substituted. Owner source,
    # count1 and the canonical map are server-owned compatibility inputs.
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',rule['buff_template'],0,owner,0.,1,0,0.,False,rule['factor'],1.,False,-1,0,0,row['start'],row['end'])

def snapshot(owner,rows,*,profiles=None):
    groups=[catalog()[r['template']].get('supplemental_group',0)for r in rows if not r.get('_silver')]
    if len(rows)>5 or len(groups)>3 or len(groups)!=len(set(groups))or any(g not in(0,310777,722990)for g in groups)or sum(bool(r.get('_silver'))for r in rows)>2 or len({r['template']for r in rows})!=len(rows):raise ValueError('Finite world snapshot groups')
    data=struct.pack('>I',len(rows))+b''.join(world_row(owner,r)for r in rows)
    if profiles is None:return Event(0x201,kind=0x3a2,payload=data)
    if not isinstance(profiles,tuple) or len(profiles)!=2 or any(not isinstance(v,bytes)or len(v)!=28 for v in profiles):raise ValueError('Original world base profiles')
    return Event(0x201,kind=0x3a3,payload=struct.pack('>Q',owner)+data+b''.join(profiles))
