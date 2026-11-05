"""Native 18C/18D shapes; payment handler is behind an explicit feature gate."""
import struct
from els_server.domain.fashion_state import record

MAX_ITEMS=397


def request(payload):
    if not isinstance(payload,bytes) or len(payload)<10:raise ValueError('Repair request length')
    count=struct.unpack_from('>I',payload)[0]
    if not 1<=count<=MAX_ITEMS or len(payload)!=10+8*count:raise ValueError('Repair request vector')
    uids=struct.unpack_from('>'+str(count)+'Q',payload,4)
    if len(set(uids))!=count or any(not 0<u<2**63 for u in uids):raise ValueError('Repair request UIDs')
    flag_a,flag_b,form=struct.unpack_from('>BBi',payload,4+count*8)
    if flag_a not in (0,1) or flag_b not in (0,1) or form not in (0,1):raise ValueError('Repair request context')
    return dict(uids=uids,flag_a=flag_a,flag_b=flag_b,form=form)


def acknowledgement(ed,items=(),result=0,vp=0,reserved=0):
    if type(ed) is not int or not 0<=ed<2**63:raise ValueError('Repair ED')
    if any(type(v) is not int or not -(2**31)<=v<2**31 for v in (result,vp,reserved)):raise ValueError('Repair header fields')
    if not isinstance(items,(list,tuple)) or len(items)>MAX_ITEMS:raise ValueError('Repair reply count')
    positions=set();uids=set();records=[]
    for item in items:
        pos=(item['group'],item['slot'])
        if pos in positions or item['uid'] in uids:raise ValueError('Repair reply duplicate')
        positions.add(pos);uids.add(item['uid']);records.append(record(item))
    return struct.pack('>iQiiI',result,ed,vp,reserved,len(records))+b''.join(records)
