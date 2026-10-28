"""Original 8A32AB..8A34C9 pet source selection, before option processing."""
from functools import lru_cache
from types import MappingProxyType
import hashlib,json,struct
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='483f75c67e13b3c99f4d0811542ba0b2dbf35f3cf75cac9df819d055a86111ad'
TEMPLATE_SHA256='9b39fe308c66387f1fd75777f2260b76af1b672bf8f219c2c6e3ff9cfc5bc9f5'
ENUM_SHA256='6d3ba2fd8c98c8eb0fd43756843356fe530da79e4dd66cbdfcf4fd17ffc4c3f8'

def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original pet source required')
    value=json.loads(raw)
    if (value['schema']!=1 or value['source_sha256']!=TEMPLATE_SHA256
            or value['enum_sha256']!=ENUM_SHA256 or len(value['definitions'])!=331):
        raise ValueError('Original pet source coverage differs')
    return MappingProxyType({int(k):MappingProxyType(dict(status=tuple(v['status']),
        auras=tuple(tuple(a)for a in v['auras'])))for k,v in value['definitions'].items()})

@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-pet-attribute-sources.json').read_bytes())

def option_ids(pet, *, excluded):
    """Keep accessory socket IDs ahead of cumulative aura groups; no dedup.

    The caller must bind the original collector exclusion flag explicitly.
    Pet equipment templates are not option IDs: D9C550 decodes each map value
    as (template,socket), and 8A3310 reads the second word at node+24.
    """
    if type(excluded)is not bool:raise ValueError('Explicit original pet exclusion flag required')
    if pet is None or excluded:return ()
    unit=pet['unit'];step=pet['step'];satiety=pet['satiety']
    if (type(unit)is not int or type(step)is not int or type(satiety)is not int
            or not 0<=satiety<=4800):raise ValueError('Invalid owned pet attribute source')
    definition=catalog()[unit]
    if not 0<=step<len(definition['status']):raise ValueError('Pet source has no native status for this stage')
    equipment=pet.get('equipment',{})
    if any(type(slot)is not int or slot not in(1,2)for slot in equipment):
        raise ValueError('Unsupported owned pet equipment slot')
    result=[]
    for slot in sorted(equipment):
        socket=equipment[slot]['socket']
        if type(socket)is not int or not 0<=socket<2**31:raise ValueError('Pet socket option identity')
        result.append(socket)
    f32=lambda n:struct.unpack('<f',struct.pack('<f',n))[0]
    if f32(f32(satiety)/4800.)>=f32(.4):
        for group in definition['auras'][:definition['status'][step]]:result.extend(group)
    return tuple(result)
