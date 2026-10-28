"""Original world BuffManager option lists for explicit qualified active IDs."""
from functools import lru_cache
from types import MappingProxyType
import hashlib,json
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='04f9a66d07ef5566c4c7585ffa94ecfc27b1a003aaa56a7f102701f039d95e70'
SOURCES=(('BuffTemplet.lua','3306d1b6d306c262df206282a54cf4b0fedb9a32d2b4f7675766eb27d2c8bab3'),
         ('BuffTemplet_INT.lua','1e5db91a362e63650f485ed93116e4e85b08b041ffe5e74bad079ef6301de5f3'))

def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original world BuffManager source required')
    value=json.loads(raw)
    if (value['schema']!=2 or value['sources']!=[dict(name=k,sha256=v)for k,v in SOURCES]
            or len(value['definitions'])!=383):
        raise ValueError('Original world BuffManager source coverage differs')
    return MappingProxyType({int(k):tuple(v)for k,v in value['definitions'].items()})

@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-world-buff-attribute-sources-v2.json').read_bytes())

def option_ids(active_ids):
    # These must come from the qualified active-vector producer. A persisted
    # world row, elapsed timer or raw buff factor is not implicitly that ID.
    if type(active_ids)is not tuple or len(active_ids)>1024:
        raise ValueError('Explicit bounded active world-buff IDs required')
    result=[]
    for identity in active_ids:
        if type(identity)is not int or identity not in catalog():raise ValueError('Unqualified active world-buff identity')
        result.extend(catalog()[identity])
    return tuple(result)
