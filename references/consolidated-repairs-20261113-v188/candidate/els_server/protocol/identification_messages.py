"""Original 438/439 identification and 43A/43B scroll reset."""
import struct
from els_server.domain.fashion_state import record,empty_record
def request(kind,wire):
 if kind==0x438:
  if not isinstance(wire,bytes) or len(wire)!=17:raise ValueError('Identification request size')
  uid,flag,count,mode=struct.unpack('>QB Ii',wire)
  if (flag,count)!=(0,0) or mode not in(0,1):raise ValueError('Unsupported identification mode')
  # 221E6B0 takes the batch checkbox and passes BATCH_TYPE=1 (pet gems)
  # through 2269180 into the final int32. Flag and option vector stay zero.
  material=mode
 elif kind==0x43a:
  if not isinstance(wire,bytes) or len(wire)!=16:raise ValueError('Identification reset size')
  material,uid=struct.unpack('>QQ',wire)
  if not 0<material<2**63 or material==uid:raise ValueError('Identification reset material')
 else:raise ValueError('Unknown identification request')
 if not 0<uid<2**63:raise ValueError('Identification equipment UID')
 return uid,material
def acknowledgement(kind,ed=0,changes=(),result=0):
 if kind not in (0x438,0x43a):raise ValueError('Identification reply kind')
 rows=list(changes)
 return struct.pack('>i',(1268) if result in (-1, 2005) else result)+(struct.pack('>Q',ed) if kind==0x438 else b'')+struct.pack('>I',len(rows))+b''.join(empty_record(*p) if i is None else record(i) for p,i in rows)
