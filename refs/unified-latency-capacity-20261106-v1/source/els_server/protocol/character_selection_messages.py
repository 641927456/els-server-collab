"""CN DX11 D30/D31: deployment vector<Q> and complete order list<Q>."""
import struct
from els_server.protocol.protocol_codec import Event

MAX_DEPLOYED=5
MAX_CHARACTERS=16  # Existing local capacity, not an official account-slot claim.

def validate_selection(deployed,order,owned):
    deployed=tuple(deployed);order=tuple(order);owned=tuple(owned)
    if len(deployed)>MAX_DEPLOYED or len(order)>MAX_CHARACTERS:raise ValueError('Selection capacity')
    if any(type(uid) is not int or not 1001<=uid<2**63 for uid in owned):raise ValueError('Owned UID')
    if any(type(uid) is not int or (uid!=0 and uid not in owned) for uid in deployed):raise ValueError('Unowned deployment')
    if len(set(uid for uid in deployed if uid))!=sum(bool(uid) for uid in deployed):raise ValueError('Duplicate deployment')
    if any(type(uid) is not int for uid in order) or len(set(order))!=len(order) or set(order)!=set(owned):raise ValueError('Incomplete character order')
    return deployed,order

def request(payload):
    if len(payload)<8:raise ValueError('Selection request length')
    count=struct.unpack_from('>I',payload)[0]
    if count>MAX_DEPLOYED or len(payload)<8+8*count:raise ValueError('Deployment length')
    deployed=struct.unpack_from('>'+str(count)+'Q',payload,4)
    offset=4+8*count;count=struct.unpack_from('>I',payload,offset)[0];offset+=4
    if count>MAX_CHARACTERS or len(payload)!=offset+8*count:raise ValueError('Order length/trailing bytes')
    return deployed,struct.unpack_from('>'+str(count)+'Q',payload,offset)

def ack(deployed=(),order=(),result=0):
    # 13AD960 reads i32 result, vector<Q>, list<Q>; successful consumer copies
    # list to manager+130 and vector to manager+118, then refreshes the scene.
    deployed=tuple(deployed);order=tuple(order)
    body=struct.pack('>iI',result,len(deployed))+b''.join(struct.pack('>Q',uid) for uid in deployed)
    body+=struct.pack('>I',len(order))+b''.join(struct.pack('>Q',uid) for uid in order)
    return Event(0x201,kind=0xd31,payload=body)
