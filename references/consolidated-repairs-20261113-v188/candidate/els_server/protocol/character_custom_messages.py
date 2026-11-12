"""c881 original 4CB/4CC/4CD, 2A owned map and 18E actor selection wire."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.character_custom import canonical,slot_value,selection_type,custom_type,COUNTS

def _u32(n):return struct.pack('>I',n)
def _text(s):
    raw=s.encode('utf-16le')
    return _u32(len(raw))+raw

def info(value):
    if value!=canonical(value.get('custom_id'),variant=value.get('variant'),ability=value.get('ability'),date1=value.get('date1'),date2=value.get('date2')):raise ValueError('Noncanonical permanent custom tuple')
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
    variant=struct.unpack_from('>i',payload,len(payload)-4)[0]
    ability=struct.unpack_from('>i',payload,9)[0]
    dates=[];offset=13
    for _ in range(2):
        if offset+4>len(payload):raise ValueError('Custom Apply date length')
        count=struct.unpack_from('>I',payload,offset)[0];offset+=4
        if count>96 or count%2 or offset+count>len(payload):raise ValueError('Custom Apply date bytes')
        dates.append(payload[offset:offset+count].decode('utf-16le'));offset+=count
    if offset+4!=len(payload):raise ValueError('Custom Apply tuple boundary')
    value=canonical(custom_id,variant=variant,ability=ability,date1=dates[0],date2=dates[1])
    if payload!=selection_map({slot:value}):raise ValueError('Client custom tuple differs from registered canonical value')
    return slot,value

def acknowledgement(values=None,result=0):
    return Event(0x201,kind=0x4cc,payload=struct.pack('>i',(21) if result == -1 else result)+selection_map(values or {}))

def registered(value):
    family=custom_type(value['custom_id'])
    if family not in COUNTS:raise ValueError('Unsupported custom registration type')
    return Event(0x201,kind=0x4cd,payload=bytes(4)+bytes([family])+info(value))

def actor_map(values):
    # Native DB2880: selected slot -> vector<custom tuple>.
    from els_server.domain import ariel_attendance_mark as mark
    rows=[]
    for slot,value in sorted(values.items()):
        if value['custom_id']==mark.MARK:
            mark.selection({slot:value})
            raw=mark.info(value)
        else:raw=info(slot_value(slot,value))
        rows.append(bytes([slot])+_u32(1)+raw)
    return _u32(len(values))+b''.join(rows)

def selected_notice(uid,title,values):
    if type(uid) is not int or not 1001<=uid<2**63 or type(title) is not int or not 0<=title<2**31:
        raise ValueError('Custom actor identity/title')
    return Event(0x201,kind=0x18e,payload=struct.pack('>QIi',uid,0,title)+actor_map(values))

def opening_information(cash_catalog):
    """23AD020: two cash-sale ID vectors, no result/status prefix.

    The existing D79 authority currently publishes no normal cash products.
    Fail closed if that authority changes: never publish stale hardcoded
    availability or substitute the independent ED catalog/owned SQL state.
    """
    if (not isinstance(cash_catalog,Event)or cash_catalog.event_id!=0x201
        or cash_catalog.kind!=0xd79 or cash_catalog.payload!=b'\x01'+bytes(36)):
        raise ValueError('Custom opener cash catalog contract changed')
    return Event(0x201,kind=0x635,payload=bytes(8))

def socket_request(payload):
    # Original32CEE90/2EE70E0/22611D0/C595C0 use219:
    # scroll instance UID (zero for free), CustomID, type3/15, chosen SocketID.
    if not isinstance(payload,bytes)or len(payload)!=29:return None
    uid,cid,family,ability,length,flag=struct.unpack('>QQiiIB',payload)
    if not cid or family not in(3,15):return None
    if uid>=2**63 or cid>=2**31 or ability<=0 or length or flag:raise ValueError('Custom socket request shape')
    return uid,cid,family,ability
