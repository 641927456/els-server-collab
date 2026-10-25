"""Pinned c881 type3 status/attend/reward/makeup and independent cash wire."""
from datetime import datetime,timezone,timedelta
import struct
from els_server.protocol.protocol_codec import Event

def text(value):
    raw=value.encode('utf-16le')
    if len(raw)>256:raise ValueError('Ariel string bound')
    return struct.pack('>I',len(raw))+raw
def vector(values):
    if not isinstance(values,(list,tuple))or len(values)>128 or any(type(v)is not int or not -(2**31)<=v<2**31 for v in values):raise ValueError('Ariel vector bound')
    return struct.pack('>I',len(values))+b''.join(struct.pack('>i',v)for v in values)
def date(moment):return datetime.fromtimestamp(moment,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
def wallet(value):
    from els_server.storage.ariel_cash import MAX_CASH
    if type(value)is not int or not 0<=value<=MAX_CASH:raise ValueError('Cash wire balance')
    # Unfiltered native refresh, index-1 does not alter CashShop+6D4.
    # Default selector1 reads slot1 (wire17), not total+9C or legacy wire4.
    return Event(0x201,kind=0x1b3,payload=struct.pack('>iIBiIIII',0,0,0,-1,0,value,0,0))
def status(value):
    count=value['attended'];claims=value['claimed'];expires=value['expires_at'];ready=value['ready_at']
    if(type(count)is not int or not 0<=count<=15 or len(claims)!=15 or any(type(v)is not int or v not in(0,1)for v in claims)
       or type(expires)is not int or not 0<=expires<2**40 or type(ready)is not int or not 0<=ready<2**40):raise ValueError('Ariel state wire boundary')
    # Normal bounded-date branch: flagfalse; client3668F80 derives active state
    # from the exact date string. The no-period constructor index is-1.
    payload=struct.pack('>iB',3,0)+vector([])+struct.pack('>i',count-1)+vector(claims)
    payload+=text(date(expires)if expires else '')+struct.pack('>Q',ready)
    return Event(0x201,kind=0xc89,payload=payload)
def request(kind,payload):
    if kind not in(0xc8c,0xc8e,0xc90)or not isinstance(payload,bytes)or len(payload)!=(8 if kind==0xc8e else 4):raise ValueError('Ariel native request width')
    if struct.unpack_from('>i',payload)[0]!=3:raise ValueError('Unqualified attendance type')
    if kind==0xc8e:
        index=struct.unpack_from('>i',payload,4)[0]
        if not 0<=index<15:raise ValueError('Ariel reward grid index')
        return index
    return None
def acknowledgement(kind,result=0):
    if kind not in(0xc8c,0xc8e,0xc90):raise ValueError('Ariel acknowledgement kind')
    return Event(0x201,kind=kind+1,payload=struct.pack('>i',result))
def inventory(items,changed):
    from els_server.domain.fashion_state import move_ack
    pairs=list(changed)+[((i['group'],i['slot']),i)for i in items]
    if len({p for p,i in pairs})!=len(pairs):raise ValueError('Ariel duplicate changed position')
    return [Event(0x201,kind=0x105,payload=move_ack(pairs))]if pairs else []
