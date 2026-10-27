"""Original8A2A10..8A2FDF per-item option collection before its callback.

The caller supplies an already eligible worn instance and the separately
qualified current activation flags. This collector never changes ownership,
selects worn items, resolves an option definition or applies a stat twice.
"""
from functools import lru_cache
import struct


@lru_cache(maxsize=1)
def canonical_circuit_state():
    """Unmodified canonical writer's trailing value; not a guessed flag."""
    from els_server.domain.inventory_items import fixture
    return circuit_state_from_seed(fixture())


def circuit_state_from_seed(source):
    raw=bytes.fromhex(source['wire_hex'])
    field=next(v for v in source['fields']if int(v['offset'],0)==0x3ec)
    return struct.unpack_from('>Q',raw,field['wire_offset'])[0]&0xffffffff


def template_level(record):
    if type(record)is not bytes or len(record)!=232:
        raise ValueError('Current complete original item template required')
    return record[0xd1]

def collect(vectors,properties,template_options,*,character_level,template_level,
            allow26,allow27,circuit_state):
    if (type(character_level)is not int or not 0<=character_level<2**31
            or type(template_level)is not int or not 0<=template_level<=255
            or type(circuit_state)is not int or not 0<=circuit_state<2**32
            or type(allow26)is not bool or type(allow27)is not bool):
        raise ValueError('Explicit original item level/activation inputs required')
    if type(properties)is not tuple or any(type(row)is not tuple or len(row)!=6
            or any(type(v)is not int or not 0<=v<2**32 for v in row)
            for row in properties):
        raise ValueError('Original six-word property rows required')
    def values(row):
        if type(row)is not tuple or any(type(v)is not int or not 0<=v<2**31 for v in row):
            raise ValueError('Ordered nonnegative int32 option IDs required')
        return row
    result=list(values(vectors[0x78]))
    result.extend(values(template_options))
    for offset in(0x60,0xa0,0xb8,0x168,0xe8,0x100,0x118,0x130,0xd0):
        result.extend(values(vectors[offset]))
    # Fresh canonical constructors set every legacy pair flag to1; qualified
    # empty mutations are enforced by native_item_option_vectors.project.
    groups=vectors[0x158]
    if any(type(key)is not int for key in groups):
        raise ValueError('Original ordered skill-group keys required')
    for key in sorted(groups):
        result.extend(values(groups[key]))
    for offset in(0x1a8,0x1c8,0x218):
        result.extend(values(vectors[offset]))
    present={row[0]for row in properties}
    if 0x4a in present and allow26:result.extend(values(vectors[0x248]))
    if 0x4e in present and allow27:result.extend(values(vectors[0x2a8]))
    if 0x52 in present:result.extend(values(vectors[0x2c0]))
    if 0x56 in present and 0x57 in present:result.extend(values(vectors[0x200]))
    if 0x59 in present and circuit_state:result.extend(values(vectors[0x2f8]))
    return tuple(result),template_level or character_level
