"""Original Camilla20-fragment recipe, independent of local racing odds."""
import functools,json,struct
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def catalog():
    p=json.loads((PROJECT_ROOT/'els_server/data/mount_racing_exchange.json').read_bytes())
    if (p['schema_version'],p['house'],p['exchange_type'],p['source'],p['source_quantity'],p['destination'],p['quantity'],p['rate'])!=(1,40016,1,714109,20,714108,1,100):
        raise ValueError('Original racing crystal exchange')
    if p['original_call']['arguments'][1:]!=[40016,1,714109,714108,1,100,dict(m_iServerGroupID=-1,m_iSourceQuantity=20)]:
        raise ValueError('Original racing crystal recipe')
    return p


def request(payload):
    if type(payload)is not bytes or len(payload)!=37:raise ValueError('Racing crystal223 length')
    house,uid,source,count,destination,kind,quantity,flag,index=struct.unpack('>iQiiiiiBi',payload)
    if (house,uid,source,count,destination,kind,flag,index)!=(40016,0,714109,20,0,1,1,0)or not 1<=quantity<2**31//20:
        raise ValueError('Racing crystal native recipe selection')
    catalog()
    return quantity
