"""Pinned935 request and2BE2300 saved layout; no scene or inventory authority."""
import math,struct
from els_server.protocol.protocol_codec import Event

LEGACY=('map','Q',('tuple','i','Q','i','i','i','i'))
NEW_REQUEST=('map','Q',('tuple','Q','i','i',('tuple','f','f','f'),'i'))
NEW_SAVED=NEW_REQUEST  # The trailing in-memory dword is ctor0, not serialized.
GRID=('map','i',('vec',('vec','Q')))
LAYOUT=('tuple',LEGACY,NEW_SAVED,GRID,'i','i')
REQUEST=('tuple',LEGACY,NEW_REQUEST,GRID,'i','i','i')
# Legal multi-floor layouts and four presets can exceed64KiB; retain the
# existing one-MiB secure-frame bound including its event/framing overhead.
MAX_BODY=1024*1024-128

def movement_floor(payload):
 # Original2448F30 puts Game+910 in DTO+32;21152A0 serializes it
 # after the existing movement DTO, also used by the ordinary town writer.
 from els_server.storage.local_state import movement_location
 if type(payload)is not bytes:raise ValueError('Housing movement bytes')
 board,progress,xyz=movement_location(payload,'dx11_260923')
 floor=struct.unpack_from('>i',payload,len(payload)-4)[0]
 if not 0<=floor<=2 or not 0<=board<255 or not 0<=progress<=100 or any(not math.isfinite(v)or abs(v)>1000000 for v in xyz):raise ValueError('Housing current movement/floor')
 return floor


def encode(schema,value):
 if isinstance(schema,str):
  if schema=='str':
   if type(value)is not str or '\x00'in value:raise ValueError('Housing native string')
   raw=value.encode('utf-16-le',errors='strict')
   if len(raw)>65534:raise ValueError('Housing native string size')
   return struct.pack('>I',len(raw))+raw
  if schema=='bool':
   if type(value)is not bool:raise ValueError('Housing native bool')
   return bytes([value])
  if schema in('f','d'):
   if type(value)not in(int,float)or not math.isfinite(value):raise ValueError('Housing finite coordinate')
  elif type(value)is not int:raise ValueError('Housing native integer')
  try:return struct.pack('>'+schema,value)
  except(struct.error,OverflowError):raise ValueError('Housing scalar bound')from None
 if schema[0]=='tuple':
  if type(value)is not tuple or len(value)!=len(schema)-1:raise ValueError('Housing native tuple')
  parts=[encode(s,v)for s,v in zip(schema[1:],value)]
 elif schema[0]in('map','vec'):
  if type(value)is not list or len(value)>560:raise ValueError('Housing container bound')
  if schema[0]=='vec':parts=[struct.pack('>I',len(value)),*[encode(schema[1],v)for v in value]]
  else:
   if any(type(v)is not tuple or len(v)!=2 for v in value):raise ValueError('Housing map pair')
   keys=[k for k,v in value]
   if any(type(k)is not int for k in keys)or keys!=sorted(set(keys)):raise ValueError('Housing unique ordered map')
   parts=[struct.pack('>I',len(value)),*[encode(schema[1],k)+encode(schema[2],v)for k,v in value]]
 else:raise ValueError('Unknown housing schema')
 raw=b''.join(parts)
 if len(raw)>MAX_BODY:raise ValueError('Housing payload bound')
 return raw

def decode(schema,payload):
 if type(payload)is not bytes or len(payload)>MAX_BODY:raise ValueError('Housing payload bound')
 pos=0;nodes=0
 def read(s):
  nonlocal pos,nodes
  nodes+=1
  if nodes>16384:raise ValueError('Housing nested container budget')
  if isinstance(s,str):
   if s=='str':
    n=read('I')
    if n>65534 or n%2 or pos+n>len(payload):raise ValueError('Housing native string length')
    v=payload[pos:pos+n].decode('utf-16-le',errors='strict');pos+=n
    if '\x00'in v:raise ValueError('Housing native string NUL')
    return v
   if s=='bool':
    v=read('B')
    if v not in(0,1):raise ValueError('Housing native bool')
    return bool(v)
   size=struct.calcsize('>'+s)
   if pos+size>len(payload):raise ValueError('Truncated housing field')
   v=struct.unpack_from('>'+s,payload,pos)[0];pos+=size
   if s in('f','d')and not math.isfinite(v):raise ValueError('Housing nonfinite coordinate')
   return v
  if s[0]=='tuple':return tuple(read(v)for v in s[1:])
  count=read('I')
  if count>560:raise ValueError('Housing container count')
  if s[0]=='vec':return[read(s[1])for _ in range(count)]
  rows=[(read(s[1]),read(s[2]))for _ in range(count)];keys=[k for k,v in rows]
  if keys!=sorted(set(keys)):raise ValueError('Housing noncanonical map')
  return rows
 value=read(schema)
 if pos!=len(payload)or encode(schema,value)!=payload:raise ValueError('Housing trailing or changed native bytes')
 return value

def empty_layout(floor=0):return([],[],[],0,floor)

def save_ack(layout,*,result=0,maximum=0,selected=0):
 #3291290:result,full layout,existing furniture rewards,inventory delta,
 #placement set,bool,two current expansion/preset indexes. No economy reward.
 raw=struct.pack('>i',result)+encode(LAYOUT,layout)+bytes(4+4+4+1)+struct.pack('>ii',maximum,selected)
 if len(raw)>MAX_BODY:raise ValueError('Housing936 bound')
 return Event(0x201,kind=0x936,payload=raw)
