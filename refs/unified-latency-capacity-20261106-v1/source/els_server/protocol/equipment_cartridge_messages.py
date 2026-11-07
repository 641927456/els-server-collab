"""Original D4D..D55 wire shapes only; no cartridge operations are enabled.

IDs/levels/points follow the pinned finite19/6/50000 tables. UID bounds and
72 changed positions are this server's serialization limits. This codec does
not decide ownership, account sharing, material counts, costs or outcomes.
"""
import struct
from els_server.protocol.protocol_codec import Event

REQUEST_LENGTHS={0xd4e:8,0xd50:12,0xd52:8,0xd54:4}
ACK_KINDS=frozenset((0xd4f,0xd51,0xd53,0xd55))
MAX_CHANGED_RECORDS=72

def _integer(value,minimum,maximum,label):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError('Cartridge '+label)
    return value

def request(kind,payload):
    if type(kind) is not int or kind not in REQUEST_LENGTHS:
        raise ValueError('Cartridge request kind')
    if type(payload) is not bytes or len(payload)!=REQUEST_LENGTHS[kind]:
        raise ValueError('Cartridge request length/type')
    if kind==0xd54:
        return (_integer(struct.unpack('>i',payload)[0],1,19,'ID'),)
    instance=struct.unpack_from('>Q',payload)[0]
    _integer(instance,1,2**63-1,'instance UID')
    if kind==0xd50:
        return instance,_integer(struct.unpack_from('>i',payload,8)[0],1,19,'ID')
    return (instance,)

def collection_wire(rows):
    if type(rows) is not dict or len(rows)>19:
        raise ValueError('Cartridge collection')
    for identity,pair in rows.items():
        _integer(identity,1,19,'collection ID')
        if type(pair) not in (tuple,list) or len(pair)!=2:
            raise ValueError('Cartridge collection pair')
        _integer(pair[0],0,2**63-1,'bound UID')
        _integer(pair[1],1,6,'level')
    return struct.pack('>I',len(rows))+b''.join(
        struct.pack('>iQi',identity,*rows[identity]) for identity in sorted(rows))

def _changes_wire(changes):
    from els_server.domain.fashion_state import record,empty_record
    from els_server.domain.bag_capacity import wire_limit
    if type(changes) not in (tuple,list) or len(changes)>MAX_CHANGED_RECORDS:
        raise ValueError('Cartridge changed positions')
    positions=set();encoded=[]
    for row in changes:
        if type(row) not in (tuple,list) or len(row)!=2:
            raise ValueError('Cartridge change row')
        position,item=row
        if type(position) not in (tuple,list) or len(position)!=2:
            raise ValueError('Cartridge change position')
        group,slot=position
        _integer(group,1,29,'bag group')
        _integer(slot,0,wire_limit(group)-1,'bag slot')
        position=(group,slot)
        if position in positions:raise ValueError('Duplicate cartridge changed position')
        positions.add(position)
        if item is None:encoded.append(empty_record(group,slot))
        else:
            if type(item) is not dict or (item.get('group'),item.get('slot'))!=position:
                raise ValueError('Cartridge changed item position mismatch')
            encoded.append(record(item))
    return struct.pack('>I',len(encoded))+b''.join(encoded)

def state(rows,points):
    points=_integer(points,0,50000,'points')
    return Event(0x201,kind=0xd4d,payload=collection_wire(rows)+struct.pack('>Q',points))

def acknowledge(kind,*,result,identity,rows,changes=(),points=None,ed=None):
    if type(kind) is not int or kind not in ACK_KINDS:
        raise ValueError('Cartridge acknowledgement kind')
    _integer(result,-2**31,2**31-1,'result')
    # Native parsers also accept ID0 in an empty/sentinel acknowledgement.
    _integer(identity,0,19,'acknowledgement ID')
    with_points=kind in (0xd4f,0xd55)
    if with_points:_integer(points,0,50000,'points')
    elif points is not None:raise ValueError('Cartridge acknowledgement has no points field')
    if kind==0xd55:_integer(ed,0,2**63-1,'ED')
    elif ed is not None:raise ValueError('Cartridge acknowledgement has no ED field')
    wire=struct.pack('>ii',result,identity)+collection_wire(rows)+_changes_wire(changes)
    if with_points:wire+=struct.pack('>Q',points)
    if kind==0xd55:wire+=struct.pack('>Q',ed)
    return Event(0x201,kind=kind,payload=wire)
