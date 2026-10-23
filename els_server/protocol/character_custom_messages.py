"""c881 original 4CB/4CC/4CD, 2A owned map and 18E actor selection wire."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.character_custom import canonical,slot_value,selection_type,custom_type,COUNTS

def _u32(n):return struct.pack('>I',n)
def _text(s):
    raw=s.encode('utf-16le')
    return _u32(len(raw))+raw

def info(value):
    if value!=canonical(value.get('custom_id')):raise ValueError('Noncanonical permanent custom tuple')
    return struct.pack('>ii',value['custom_id'],value['ability'])+_text(value['date1'])+_text(value['date2'])+struct.pack('>i',value['variant'])

def selection_map(values):
    if not isinstance(values,dict):raise ValueError('Unsupported custom slot')
    return _u32(len(values))+b''.join(bytes([k])+info(slot_value(k,v)) for k,v in sorted(values.items()))

def owned_map(values):
    if not isinstance(values,dict) or set(values)-set(COUNTS) or any(type(k) is not int for k in values):raise ValueError('Unsupported owned custom type')
    result=_u32(len(values))
    for key,rows in sorted(values.items()):
        if (not isinstance(rows,(tuple,list)) or not rows or len(rows)>COUNTS[key] or len({v['custom_id'] for v in rows})!=len(rows)
            or any(v['custom_id']==0 or custom_type(v['custom_id'])!=key for v in rows)):raise ValueError('Owned custom list')
        result+=bytes([key])+_u32(len(rows))+b''.join(info(v) for v in rows)
    return result

def request(payload):
    # Retain the existing value-only helper; storage also needs the selected key.
    return request_slot(payload)[1]

def request_slot(payload):
    # 11D98B0/11F48D0 sends exactly one selected slot per Apply.
    if not isinstance(payload,bytes) or len(payload)>256 or len(payload)<5 or payload[:4]!=b'\x00\x00\x00\x01':
        raise ValueError('Permanent custom Apply shape')
    slot=payload[4];selection_type(slot)
    if len(payload)<13:raise ValueError('Permanent custom Apply tuple')
    custom_id=struct.unpack_from('>i',payload,5)[0]
    value=canonical(custom_id)
    if payload!=selection_map({slot:value}):raise ValueError('Client custom tuple differs from registered canonical value')
    return slot,value

def acknowledgement(values=None,result=0):
    return Event(0x201,kind=0x4cc,payload=struct.pack('>i',result)+selection_map(values or {}))

def registered(value):
    family=custom_type(value['custom_id'])
    if family not in COUNTS:raise ValueError('Unsupported custom registration type')
    return Event(0x201,kind=0x4cd,payload=bytes(4)+bytes([family])+info(value))

def selected_notice(uid,title,values):
    if type(uid) is not int or not 1001<=uid<2**63 or type(title) is not int or not 0<=title<2**31:
        raise ValueError('Custom actor identity/title')
    # 30D5C50 ->214E6C0: this i32 is the equipped title. Reuse the current
    # authoritative snapshot; zero is valid only when no eligible title exists.
    # 18E keys are selected slots, not the 2A registration/owned type keys.
    selection_map(values)
    lists=_u32(len(values))+b''.join(bytes([k])+_u32(1)+info(v)for k,v in sorted(values.items()))
    return Event(0x201,kind=0x18e,payload=struct.pack('>QI',uid,0)+struct.pack('>i',title)+lists)
