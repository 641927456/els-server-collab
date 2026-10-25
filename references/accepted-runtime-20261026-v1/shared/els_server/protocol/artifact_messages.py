"""Original 131F100 / 1315690 / 215A2D0 wire layouts."""
import struct
from els_server.protocol.protocol_codec import Event

def potential_request(payload):
 if not isinstance(payload,bytes) or len(payload)!=9:raise ValueError('Artifact request length')
 index,reset,chosen=struct.unpack('>iBi',payload)
 if index not in range(4) or reset not in (0,1) or chosen<0:raise ValueError('Artifact request fields')
 return index,bool(reset),chosen

def consumable_request(payload):
 # 2260FD0 / 2224DE0: the second uint64 carries the selected bulk count.
 # A plain click sends zero, meaning one. It is not a target character UID.
 if not isinstance(payload,bytes) or len(payload)!=29:raise ValueError('Artifact item request length')
 uid,count,a,b,n,flag=struct.unpack('>QQiiIB',payload)
 if not 0<uid<2**63 or not 0<=count<=99 or a or b or n or flag:raise ValueError('Artifact item request fields')
 return uid,count or 1

def potential_ack(character=None,changes=(),reset=False,result=0):
 from els_server.domain.fashion_state import empty_record,record
 choices=character['artifact']['potentials'] if character else []
 delta=struct.pack('>I',len(changes))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in changes)
 payload=struct.pack('>iI',result,len(choices))+b''.join(struct.pack('>i',v) for v in choices)+delta+struct.pack('>B',reset)
 return Event(0x201,kind=0x908,payload=payload)

def notice(character,evolved=False):
 from els_server.domain.character_rules import artifact_wire
 return Event(0x201,kind=0x904,payload=struct.pack('>Q',character['uid'])+artifact_wire(character)+struct.pack('>B',evolved))

def equipment_map(items):
 from els_server.domain.inventory_items import validate_item
 from els_server.domain.fashion_state import record
 equipped=sorted((validate_item(i) for i in items if i['group']==24),key=lambda i:i['slot'])
 return struct.pack('>I',len(equipped))+b''.join(struct.pack('>i',i['slot'])+record(i) for i in equipped)
