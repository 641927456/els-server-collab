"""Immutable current KIM set definitions and shared property/option pools."""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='e07436bc98fbc447bee4097d81f73d233ffcfb2ae0256abeb3319f0eb6fd36ab'
KIM_SHA256='a3bcc9c926b19aa36f1c737ca53993b23da11c372bfd5adf3d740dc0b691ab8e'


def freeze(value):
    if type(value)is dict:return MappingProxyType({k:freeze(v)for k,v in value.items()})
    if type(value)is list:return tuple(freeze(v)for v in value)
    return value


def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified current set source required')
    value=json.loads(raw)
    if (value.get('schema')!=1 or value.get('source_sha256')!=KIM_SHA256
            or value.get('item_count')!=181836 or value.get('set_count')!=11422
            or len(value['definitions'])!=11422):
        raise ValueError('Current original set source coverage differs')
    value['definitions']={int(k):v for k,v in value['definitions'].items()}
    value['properties']={int(k):v for k,v in value['properties'].items()}
    value['options']={int(k):[r[0]for r in v]for k,v in value['options'].items()}
    return freeze(value)


@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-set-sources.json').read_bytes())


def item_pools(record):
    import struct
    if type(record)is not bytes or len(record)!=232:
        raise ValueError('Original current item record required')
    properties,options=struct.unpack_from('<2I',record,0xac)
    source=catalog()
    # A nonzero pointer missing from the qualified pool is a source mismatch,
    # never an empty effect group. The item identity is checked by its caller.
    return (source['properties'][properties]if properties else (),
            source['options'][options]if options else ())
