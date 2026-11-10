"""Current original PhotoZone DTO fields; no client protocol additions."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
def room(*,world,name,room_id=0,password='',public=True,state=0,max_slots=0,join_slots=0,bootstrap_port=0):
 I=lambda x:struct.pack('>i',x);U=lambda x:struct.pack('>I',x);Q=lambda x:struct.pack('>Q',x);H=lambda x:struct.pack('>H',x)
 data=bytes([9])+Q(room_id)+U(0)+wstring(name)
 data+=bytes([state,int(public),0])+wstring(password)+bytes([max_slots,join_slots])
 data+=wstring('127.0.0.1' if bootstrap_port else '')+H(bootstrap_port)+wstring('')
 data+=bytes([0,255,0])+I(-1)+bytes(2)+U(0)+H(world)+H(0)+Q(0)+I(0)+bytes(1)+I(0)
 data+=bytes(2)+Q(0)+Q(0)+I(0)+bytes(1)+U(0)+bytes(2)+I(0)+bytes(2)+Q(0)
 data+=U(5)+b''.join(I(k)+I(-1)for k in range(5))+bytes(1)+I(0)+Q(0)+Q(0)
 return data
def text(payload,pos,limit):
 if pos+4>len(payload):raise ValueError('PhotoZone short text')
 size=struct.unpack_from('>I',payload,pos)[0];pos+=4
 if size&1 or size>2*limit or pos+size>len(payload):raise ValueError('PhotoZone text bounds')
 value=payload[pos:pos+size].decode('utf-16le')
 if any(ord(c)<32 for c in value):raise ValueError('PhotoZone control text')
 return value,pos+size
def creation(payload):
 if len(payload)<49 or payload[:13]!=bytes([9])+bytes(12):raise ValueError('PhotoZone original creation descriptor')
 name,pos=text(payload,13,20)
 if not name or payload[pos:pos+1]!=b'\0' or payload[pos+2:pos+3]!=b'\0' or payload[pos+1]not in(0,1):raise ValueError('PhotoZone original privacy')
 public=bool(payload[pos+1]);password,end=text(payload,pos+3,64)
 if not public and not password:raise ValueError('PhotoZone private room requires password')
 at=49+len(name.encode('utf-16le'))+len(password.encode('utf-16le'))
 if at+2>len(payload):raise ValueError('PhotoZone short world')
 world=struct.unpack_from('>H',payload,at)[0]
 result=dict(name=name,public=public,password=password,world=world)
 if room(**result)!=payload:raise ValueError('PhotoZone unexpected creation fields')
 return result
def joining(payload):
 if len(payload)<12:raise ValueError('PhotoZone short join')
 uid=struct.unpack_from('>Q',payload)[0];password,end=text(payload,8,64)
 if end!=len(payload)or not 0<uid<2**63:raise ValueError('PhotoZone join descriptor')
 return uid,password
def settings(payload):
 if not payload or payload[0]not in(0,1):raise ValueError('PhotoZone settings privacy')
 name,pos=text(payload,1,20);password,pos=text(payload,pos,64)
 if not name or pos+2!=len(payload)or not payload[0]and not password:raise ValueError('PhotoZone settings shape')
 return dict(public=bool(payload[0]),name=name,password=password,world=struct.unpack_from('>H',payload,pos)[0])

def name_request(payload):
 if len(payload)<16:raise ValueError('PhotoZone name-check body')
 correlation=struct.unpack_from('>Q',payload)[0]
 name,end=text(payload,8,20)
 if not correlation or not name or end+4!=len(payload)or struct.unpack_from('>i',payload,end)[0]!=21:
  raise ValueError('PhotoZone name-check correlation/type')
 return correlation,name

def name_checked(correlation,name,result=0):
 return Event(0x201,kind=0xe45,payload=struct.pack('>iQi',result,correlation,0)+wstring(name)+struct.pack('>i',21))

def unlock_request(payload):
 if len(payload)!=10:raise ValueError('Studio unlock request length')
 source,world=struct.unpack('>QH',payload)
 if not 0<source<2**63:raise ValueError('Studio unlock ticket UID')
 return source,world

def unlocked(worlds):
 rows=sorted(worlds)
 return Event(0x201,kind=0x5ba,payload=struct.pack('>I',len(rows))+b''.join(struct.pack('>i',world)for world in rows)+b'\0')

def unlocked_ack(changes=(),result=0):
 from els_server.domain.fashion_state import empty_record,record
 payload=struct.pack('>iI',result,len(changes))+b''.join(empty_record(*position)if item is None else record(item)for position,item in changes)
 return Event(0x201,kind=0x5b9,payload=payload)
def teams(members):
 """Rows are (stable slot, native FullUser, current master)."""
 return struct.pack('>I',len(members))+b''.join(team(slot,value,master)for slot,value,master in members)

def team(i,value,master=False):return bytes([i,4,int(master)])+bytes(3)+struct.pack('>iI',0,1)+value+struct.pack('>I',0)+bytes(4)
def created(room_wire,team_wire,camera,result=0):return Event(0x201,kind=0x5a3,payload=struct.pack('>i',result)+room_wire+team_wire+wstring('')+bytes([camera]))
def joined(room_wire,own_fulluser,team_wire,camera,result=0):return Event(0x201,kind=0x5a5,payload=struct.pack('>i',result)+room_wire+own_fulluser+team_wire+wstring('')+wstring('')+struct.pack('>H',0)+wstring('')+bytes([camera]))
def listed(rooms,pages=1,result=0,total=None):return Event(0x201,kind=0x5ad,payload=struct.pack('>iIII',result,pages,len(rooms)if total is None else total,len(rooms))+b''.join(rooms))
def left(state,uid,team_wire):return Event(0x201,kind=0x5a9,payload=struct.pack('>BQiBQ',state,uid,0,0,0)+team_wire+struct.pack('>Q',0))
def changed(value,result=0,stamp=0):return Event(0x201,kind=0x5b5,payload=struct.pack('>iB',result,int(value['public']))+wstring(value['name'])+wstring(value['password'])+struct.pack('>HQ',value['world'],stamp))
def change_notice(value):return Event(0x201,kind=0x5b6,payload=bytes([value['public']])+wstring(value['name'])+struct.pack('>H',value['world']))
