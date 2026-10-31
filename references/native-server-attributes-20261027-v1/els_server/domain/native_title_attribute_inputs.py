"""Current original title's direct inputs and ordered secondary options."""
from functools import lru_cache
from types import MappingProxyType
import hashlib,json,struct
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='766cf6ca16e10fd3df197ebcc3080bea441e9286ce6345ad18d52a59c44e3df9'
TEMPLATE_SHA256='7ca4133338f85b3be4873bdcbe53945af6e121f83a446d611ca3c8e73e151734'

def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original title source required')
    value=json.loads(raw)
    if value['schema']!=1 or value['source_sha256']!=TEMPLATE_SHA256 or len(value['definitions'])!=932:
        raise ValueError('Original title source coverage differs')
    return MappingProxyType({int(k):MappingProxyType(dict(flat=tuple(v['flat']),options=tuple(v['options'])))for k,v in value['definitions'].items()})

@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-title-attribute-sources.json').read_bytes())

def inputs(identity):
    if type(identity)is not int or not 0<=identity<2**31:raise ValueError('Original effective title identity')
    if not identity:return dict(direct=(0.,)*7,options=())
    source=catalog()[identity];hp,pa,ma,pd,md=source['flat']
    f32=lambda n:struct.unpack('<f',struct.pack('<f',n))[0]
    return dict(direct=tuple(map(f32,(hp,pa,ma,0,0,pd,md))),options=source['options'])
