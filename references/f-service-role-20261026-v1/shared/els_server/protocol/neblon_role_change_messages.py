"""Original D56 UID/template and D57 result/map/full native inventory records."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.equipment_reforge_transfer_messages import _changes_wire

def request(payload):
 if type(payload)is not bytes or len(payload)!=12:raise ValueError('Neblon D56 original request size')
 uid,template=struct.unpack('>Qi',payload)
 if not 0<uid<2**63 or template<=0:raise ValueError('Neblon D56 UID/template')
 return uid,template

def acknowledgement(template=0,changes=(),result=0):
 if type(result)is not int or not -2**31<=result<2**31:raise ValueError('Neblon D57 result')
 vector,identities=_changes_wire(changes)
 if result:
  if changes or template:raise ValueError('Rejected Neblon transformation has no changes')
  pairs=b'';count=0
 else:
  if type(template)is not int or template<=0 or not identities:raise ValueError('Successful Neblon target template')
  targets=[i for point,i in changes if i is not None and i['template']==template]
  if len(targets)!=1 or targets[0]['group']!=1 or targets[0]['count']!=1:raise ValueError('Exact transformed Neblon armor record')
  count=1;pairs=struct.pack('>ii',template,1)
 payload=struct.pack('>iI',result,count)+pairs+vector
 if len(payload)+64>1024*1024:raise ValueError('Neblon response frame bound')
 return Event(0x201,kind=0xd57,payload=payload)
