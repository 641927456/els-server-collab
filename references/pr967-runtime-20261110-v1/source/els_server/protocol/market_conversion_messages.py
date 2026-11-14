"""Original 17/18/19 bool tail and 22 selected next-option, complete 6E8."""
import struct
from els_server.protocol.artifact_socket_messages import acknowledgement as full_ack
def request(payload):
 if not isinstance(payload,bytes)or len(payload)not in(18,38):raise ValueError('Market conversion native size')
 mode=struct.unpack_from('>i',payload,len(payload)-5)[0]
 if mode in(17,18,19):
  if len(payload)!=18:raise ValueError('Market conversion original empty map')
  uid,n,flag,m,tail=struct.unpack('>QIBiB',payload)
  if n or flag or tail not in(0,1)or mode==19 and tail:raise ValueError('Market conversion original flags')
  slot=value=None
 elif mode==22:
  if len(payload)!=38:raise ValueError('Market upgrade original size')
  uid,n,g,k,slot,value,flag,m,tail=struct.unpack('>QIiIiQBiB',payload)
  if(n,g,k,flag,tail)!=(1,29,1,0,1)or not 0<=slot<4 or not 0<value<2**31:raise ValueError('Market upgrade original selection')
 else:raise ValueError('Market conversion native mode')
 if not 0<uid<2**63:raise ValueError('Market conversion original target UID')
 return uid,mode,tail,slot,value
def acknowledgement(uid=0,ed=0,changes=(),*,mode,options=(),result=0):
 return full_ack(uid,ed,changes,mode=mode,option=0,options=options,result=result)
