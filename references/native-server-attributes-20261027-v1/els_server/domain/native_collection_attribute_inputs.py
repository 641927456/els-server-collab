"""Qualified current El Search Party collection options, before contribution."""
from functools import lru_cache
from types import MappingProxyType
import hashlib,json
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='f7c1a4f802b4f4e15884d397443c3e144bd98713e154f69fc36b85629c681026'
TEMPLATE_SHA256='fb6e00f3b8148e6144b8d2ce53ce3ee80d7a3574ea78845ce6e65a2b866066e8'

def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original collection source required')
    value=json.loads(raw)
    if value['schema']!=1 or value['source_sha256']!=TEMPLATE_SHA256 or len(value['definitions'])!=300:
        raise ValueError('Original collection source coverage differs')
    return MappingProxyType({tuple(map(int,k.split(':'))):tuple(v)for k,v in value['definitions'].items()})

@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-collection-attribute-sources.json').read_bytes())

def lookup(career,stage):
    if type(career)is not int or type(stage)is not int:raise ValueError('Original collection class/stage key')
    return catalog().get((career,stage),())

def option_ids(value):
    if value is None:return ()
    from els_server.domain.el_search_collection import wire
    # Existing canonical ownership/ledger reader builds this exact snapshot;
    # the wire validator also rejects unexpected synergy/preset extensions.
    wire(value)
    if not value['active']:return ()
    result=[]
    for row in value['registered']:
        key=(row['unit_class'],row['transcendental'])
        if key not in catalog():raise ValueError('Registered collection source is absent')
        result.extend(catalog()[key])
    return tuple(result)
