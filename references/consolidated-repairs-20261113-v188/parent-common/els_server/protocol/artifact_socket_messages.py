"""Original nested-map 6E7 request and 234C870 6E8 response."""
import struct
from els_server.domain.fashion_state import record,empty_record
from els_server.protocol.protocol_codec import Event
def request(payload):
 if not isinstance(payload,bytes) or len(payload)<18 or len(payload)>256:raise ValueError('Special socket request size')
 uid,count=struct.unpack_from('>QI',payload);offset=12;groups={}
 if not 0<uid<2**63 or count>4:raise ValueError('Special socket target/groups')
 for _ in range(count):
  if offset+8>len(payload):raise ValueError('Truncated socket category')
  group,n=struct.unpack_from('>iI',payload,offset);offset+=8
  if not 0<=group<32 or group in groups or n>5 or offset+n*12>len(payload):raise ValueError('Special socket nested map bound')
  values={}
  for _ in range(n):
   slot,value=struct.unpack_from('>iQ',payload,offset);offset+=12
   if not 0<=slot<5 or slot in values or value>=2**63:raise ValueError('Special socket entry bound')
   values[slot]=value
  groups[group]=values
 if offset+6!=len(payload):raise ValueError('Special socket reserved tail')
 flag,mode,reserved=struct.unpack_from('>BiB',payload,offset)
 if flag not in (0,1) or reserved:raise ValueError('Special socket flags')
 return uid,groups,bool(flag),mode
def acknowledgement(uid=0,ed=0,changes=(),mode=20,option=0,options=(),result=0):
 rows=list(changes);values=list(options)
 payload=struct.pack('>iQQI',result,uid,ed,len(rows))+b''.join(empty_record(*p) if i is None else record(i) for p,i in rows)
 payload+=struct.pack('>iiiI',mode,option,0,len(values))+b''.join(struct.pack('>i',v) for v in values)
 return Event(0x201,kind=0x6e8,payload=payload)
