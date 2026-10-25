"""Original6E7 mode17 paid18byte body and complete234C8706E8 acknowledgement."""
import struct
from els_server.protocol.artifact_socket_messages import acknowledgement as full_ack

def request(payload):
 if not isinstance(payload,bytes)or len(payload)!=18:raise ValueError('Existing conversion request size')
 uid,n,flag,mode,tail=struct.unpack('>QIBiB',payload)
 if not 0<uid<2**63 or n!=0 or flag!=0 or mode!=17 or tail!=0:raise ValueError('Only paid weapon mode17 empty map is admitted')
 return uid

def acknowledgement(uid=0,ed=0,changes=(),result=0):
 return full_ack(uid,ed,changes,mode=17,option=0,options=(),result=result)
