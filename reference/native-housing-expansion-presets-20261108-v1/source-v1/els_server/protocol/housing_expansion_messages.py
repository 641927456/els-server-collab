"""Original item use and absolute housing state notifications."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.housing_messages import _encode
from els_server.protocol.housing_layout_messages import GRID,encode

INFO=(('name','str'),('floors',('map','i',('tuple','i','i'))),('extra_presets','i'),('flag','bool'),('date','Q'))

def use_request(payload):
 if type(payload)is not bytes or len(payload)!=29:raise ValueError('Housing expansion item-use size')
 uid,target,a,b,n,flag=struct.unpack('>QQiiIB',payload)
 if not 0<uid<2**63 or target>3 or a or b or n or flag:raise ValueError('Housing expansion item-use fields')
 return uid,target

def info(floors,extra_presets):
 #93D feeds the same HousingInfo consumer as924 DTO0BA..0EF.
 return Event(0x201,kind=0x93d,payload=_encode(INFO,dict(name='',floors=sorted(floors.items()),extra_presets=extra_presets,flag=False,date=0)))

def stage(maximum,grid,floor,selected):
 return Event(0x201,kind=0x946,payload=struct.pack('>i',maximum)+encode(GRID,grid)+struct.pack('>ii',floor,selected))
