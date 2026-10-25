"""Original modern socket 1C4/1C5; no profession/helper modes admitted."""
import struct
from els_server.domain.fashion_state import record,empty_record
def request(wire):
 if not isinstance(wire,bytes) or len(wire)<18:raise ValueError('Socket request size')
 uid,count=struct.unpack_from('>QI',wire)
 if not 0<uid<2**63 or not 1<=count<=6 or len(wire)!=8+4+12*count+2+4+24:raise ValueError('Socket request bounds')
 rows=[struct.unpack_from('>iQ',wire,12+12*n) for n in range(count)]
 pos=12+12*count;a,b,n=struct.unpack_from('>BBI',wire,pos)
 if a or b or n!=6 or any(wire[pos+6:]):raise ValueError('Unimplemented socket mode')
 if len({k for k,v in rows})!=count or any(not 0<=k<6 or not 0<v<2**63 for k,v in rows):raise ValueError('Socket slots/material UID')
 return uid,dict(rows)
def acknowledgement(ed=0,uid=0,changes=(),options=(),result=0):
 rows=list(changes);values=list(options)
 return (struct.pack('>iQQI',result,ed,uid,len(rows))+
  b''.join(empty_record(*p) if i is None else record(i) for p,i in rows)+
  struct.pack('>IiI',0,0,len(values))+b''.join(struct.pack('>i',v) for v in values))

def apply_request(wire):
 if not isinstance(wire,bytes)or len(wire)<12:raise ValueError('Socket Apply request size')
 uid,count=struct.unpack_from('>QI',wire)
 if not 0<uid<2**63 or not 0<=count<=6 or len(wire)!=12+12*count:raise ValueError('Socket Apply request bounds')
 rows=[struct.unpack_from('>iQ',wire,12+12*k)for k in range(count)]
 if len({k for k,v in rows})!=count or any(not 0<=k<6 or not 0<v<2**31 for k,v in rows):raise ValueError('Socket Apply choices')
 return uid,dict(rows)

def apply_acknowledgement(uid=0,*,changes=(),result=0):
 rows=list(changes)
 return struct.pack('>iQI',result,uid,len(rows))+b''.join(empty_record(*p)if i is None else record(i)for p,i in rows)
