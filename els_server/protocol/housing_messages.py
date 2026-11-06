"""Exact native923/924 layout only; no admission, defaults or housing writer."""
import math,struct

# Keys name current packed DTO offsets, not guessed business semantics.
INFO=(('00','Q'),('08','Q'),('10','str'),('30','B'),('31','B'),
      ('32','str'),('52','i'),('56','str'),('76',('vec','Q')),('8e','Q'),('96','str'))
STATE=(('00','Q'),('08',('vec','i')),('20','i'),('24','bool'),('25','bool'),
       ('26','bool'),('27',('vec',('tuple','i','i'))),('3f','B'),('40','Q'))
PROFILE=(('00','H'),('02','str'),('22','i'),('26','i'),('2a','Q'),
         ('32','str'),('52','B'),('53','B'))
ACK=(('000','i'),('004',INFO),('0ba','str'),('0da',('map','i',('tuple','i','i'))),
     ('0ea','i'),('0ee','bool'),('0ef','Q'),('0f7','empty_map'),('107',STATE),
     ('14f',PROFILE),('1a3','bool'),('1a4',('map','i',('tuple','i','Q','d'))),
     ('1c4','bool'),('1b4','empty_map'),('1c5','empty_map'))

def _encode(schema,value):
    if isinstance(schema,str):
        if schema=='str':
            if type(value)is not str or '\x00'in value:raise ValueError('Housing native string')
            raw=value.encode('utf-16-le',errors='strict')
            if len(raw)>65534:raise ValueError('Housing native string size')
            return struct.pack('>I',len(raw))+raw
        if schema=='bool':
            if type(value)is not bool:raise ValueError('Housing native bool')
            return bytes([value])
        if schema=='empty_map':
            # These maps have proven count prefixes but their nonempty
            # furniture/unit records are outside this finite codec.
            if value!=[] or type(value)is not list:raise ValueError('Housing nonempty unresolved map')
            return bytes(4)
        if schema=='d':
            if type(value)not in(int,float)or not math.isfinite(value):raise ValueError('Housing finite double')
        elif type(value)is not int:raise ValueError('Housing native integer')
        try:return struct.pack('>'+schema,value)
        except(struct.error,OverflowError):raise ValueError('Housing scalar range')from None
    if schema[0]=='tuple':
        if type(value)is not tuple or len(value)!=len(schema)-1:raise ValueError('Housing tuple layout')
        return b''.join(_encode(s,v)for s,v in zip(schema[1:],value))
    if schema[0]in('vec','map'):
        if type(value)is not list or len(value)>1024:raise ValueError('Housing container size')
        if schema[0]=='vec':parts=[_encode(schema[1],v)for v in value]
        else:
            if any(type(row)is not tuple or len(row)!=2 for row in value):raise ValueError('Housing map pair')
            keys=[k for k,v in value]
            if keys!=sorted(set(keys)):raise ValueError('Housing canonical map keys')
            parts=[_encode(schema[1],k)+_encode(schema[2],v)for k,v in value]
        return struct.pack('>I',len(value))+b''.join(parts)
    if type(value)is not dict or set(value)!={k for k,s in schema}:raise ValueError('Housing exact DTO fields')
    return b''.join(_encode(s,value[k])for k,s in schema)

def entry_request(payload):
    # C63D60 exact U64,Int,Float3,Byte; capacity28 is not wire length25.
    if type(payload)is not bytes or len(payload)!=25:raise ValueError('Housing923 request length')
    target,scene,x,y,z,kind=struct.unpack('>Qi3fB',payload)
    if scene!=26000 or any(not math.isfinite(v)for v in(x,y,z))or not 1<=kind<=5:raise ValueError('Housing923 native fields')
    if kind in(1,4)and target!=0:raise ValueError('Housing own/random native target')
    if kind in(2,3,5)and not 0<target<2**63:raise ValueError('Housing visit native target')
    return dict(target=target,scene=scene,xyz=(x,y,z),kind=kind)

def entry_snapshot(value):
    # Every field is explicit. This function does not create initial values,
    # consume a contract, grant admission or mark objective75 as completed.
    raw=_encode(ACK,value)
    if len(raw)>65536:raise ValueError('Housing924 payload bound')
    return raw
