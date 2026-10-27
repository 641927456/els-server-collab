"""Exact current A0A/A0C request layouts, without a market source or dispatch.

Names containing offsets are deliberately opaque until their original UI/source
join is qualified. Parsing a request does not authorize or produce listings.
"""
import struct

FULL = (
    (0x00,'set_i32','template_ids'),(0x10,'u8','category'),(0x11,'u8','mode_11'),
    (0x12,'set_u8','set_12'),(0x22,'set_u8','set_22'),(0x32,'set_u8','set_32'),
    (0x42,'set_u16','set_42'),(0x52,'set_u8','set_52'),
    (0x62,'pair_u8','enchant_range'),(0x64,'pair_u8','reforge_range'),
    # The native writer emits A6 before the two physically earlier vectors.
    (0xa6,'u8','seal_count'),(0x66,'groups_i32','option_groups_66'),
    (0x7e,'groups_i32','option_groups_7e'),(0x96,'pair_u64','price_range'),
    (0xa7,'i32','cursor_template'),(0xab,'u64','cursor_price'),(0xb3,'u64','cursor_listing_id'),
    (0xbb,'u8','cursor_byte'),(0xbc,'set_i32','mount_data_ids'),
    (0xcc,'i32','cheer'),(0xd0,'i32','patience'),(0xd4,'i32','expert'),
    (0xd8,'i32','concentration'),(0xdc,'set_i32','ids_dc'),
)
BATCH = (
    (0x00,'set_i32','ids_00'),(0x10,'vector_i32','ids_10'),
    (0x28,'u8','category'),(0x29,'u8','mode_29'),
    (0x2a,'set_u8','set_2a'),(0x3a,'set_u8','set_3a'),
    (0x4a,'set_u16','set_4a'),(0x5a,'set_u8','set_5a'),
    (0x6a,'bool','flag_6a'),(0x6b,'i32','cursor_template'),
    (0x6f,'u64','cursor_price'),(0x77,'u64','cursor_listing_id'),(0x7f,'u8','cursor_byte'),
    (0x80,'set_i32','ids_80'),(0x90,'set_i32','ids_90'),
)
SCALARS={'u8':'B','u16':'H','i32':'i','u64':'Q'}

class InvalidFilter(ValueError):pass

class Reader:
    def __init__(self,payload):
        if type(payload) is not bytes:raise InvalidFilter('Request must be bytes')
        self.payload=payload;self.pos=0
    def scalar(self,kind):
        fmt='>'+SCALARS[kind];size=struct.calcsize(fmt)
        if self.pos+size>len(self.payload):raise InvalidFilter('Truncated scalar')
        value=struct.unpack_from(fmt,self.payload,self.pos)[0];self.pos+=size;return value
    def count(self,min_size):
        if self.pos+4>len(self.payload):raise InvalidFilter('Truncated count')
        n=struct.unpack_from('>I',self.payload,self.pos)[0];self.pos+=4
        if n>(len(self.payload)-self.pos)//min_size:raise InvalidFilter('Count exceeds body')
        return n
    def value(self,kind):
        if kind in SCALARS:return self.scalar(kind)
        if kind=='bool':
            value=self.scalar('u8')
            if value not in (0,1):raise InvalidFilter('Noncanonical boolean')
            return bool(value)
        if kind.startswith('pair_'):
            return tuple(self.scalar(kind[5:]) for _ in range(2))
        if kind=='groups_i32':
            return tuple(self.value('vector_i32') for _ in range(self.count(4)))
        if kind.startswith(('set_','vector_')):
            sub=kind.split('_',1)[1];size=struct.calcsize('>'+SCALARS[sub]);n=self.count(size)
            values=tuple(self.scalar(sub) for _ in range(n))
            if kind.startswith('set_') and values!=tuple(sorted(set(values))):
                raise InvalidFilter('Noncanonical native ordered set')
            return values
        raise AssertionError(kind)

def layout(kind):
    if kind==0xa0a:return FULL
    if kind==0xa0c:return BATCH
    raise InvalidFilter('Unsupported request kind')

def decode(kind,payload):
    r=Reader(payload);result={name:r.value(typ) for _,typ,name in layout(kind)}
    if r.pos!=len(payload):raise InvalidFilter('Trailing body')
    return result

def pack_value(kind,value):
    if kind in SCALARS:
        if type(value) is not int:raise InvalidFilter('Integer required')
        try:return struct.pack('>'+SCALARS[kind],value)
        except struct.error as e:raise InvalidFilter('Integer out of range') from e
    if kind=='bool':
        if type(value) is not bool:raise InvalidFilter('Boolean required')
        return bytes((int(value),))
    if kind.startswith('pair_'):
        if len(value)!=2:raise InvalidFilter('Pair required')
        return b''.join(pack_value(kind[5:],v) for v in value)
    if kind=='groups_i32':
        return struct.pack('>I',len(value))+b''.join(pack_value('vector_i32',v) for v in value)
    if kind.startswith(('set_','vector_')):
        sub=kind.split('_',1)[1];values=tuple(value)
        if kind.startswith('set_') and values!=tuple(sorted(set(values))):raise InvalidFilter('Ordered set required')
        return struct.pack('>I',len(values))+b''.join(pack_value(sub,v) for v in values)
    raise AssertionError(kind)

def encode(kind,values):
    spec=layout(kind)
    if set(values)!={name for _,_,name in spec}:raise InvalidFilter('Exact field set required')
    return b''.join(pack_value(typ,values[name]) for _,typ,name in spec)
