"""Pinned935 request and2BE2300 saved layout; no scene or inventory authority."""
import math,struct
from els_server.protocol.protocol_codec import Event

LEGACY=('map','Q',('tuple','i','Q','i','i','i','i'))
NEW_REQUEST=('map','Q',('tuple','Q','i','i',('tuple','f','f','f'),'i'))
NEW_SAVED=NEW_REQUEST  # The trailing in-memory dword is ctor0, not serialized.
GRID=('map','i',('vec',('vec','Q')))
LAYOUT=('tuple',LEGACY,NEW_SAVED,GRID,'i','i')
REQUEST=('tuple',LEGACY,NEW_REQUEST,GRID,'i','i','i')
MAX_BODY=65536

def encode(schema,value):
 if isinstance(schema,str):
  if schema in('f','d'):
   if type(value)not in(int,float)or not math.isfinite(value):raise ValueError('Housing finite coordinate')
  elif type(value)is not int:raise ValueError('Housing native integer')
  try:return struct.pack('>'+schema,value)
  except(struct.error,OverflowError):raise ValueError('Housing scalar bound')from None
 if schema[0]=='tuple':
  if type(value)is not tuple or len(value)!=len(schema)-1:raise ValueError('Housing native tuple')
  parts=[encode(s,v)for s,v in zip(schema[1:],value)]
 elif schema[0]in('map','vec'):
  if type(value)is not list or len(value)>512:raise ValueError('Housing container bound')
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
   size=struct.calcsize('>'+s)
   if pos+size>len(payload):raise ValueError('Truncated housing field')
   v=struct.unpack_from('>'+s,payload,pos)[0];pos+=size
   if s in('f','d')and not math.isfinite(v):raise ValueError('Housing nonfinite coordinate')
   return v
  if s[0]=='tuple':return tuple(read(v)for v in s[1:])
  count=read('I')
  if count>512:raise ValueError('Housing container count')
  if s[0]=='vec':return[read(s[1])for _ in range(count)]
  rows=[(read(s[1]),read(s[2]))for _ in range(count)];keys=[k for k,v in rows]
  if keys!=sorted(set(keys)):raise ValueError('Housing noncanonical map')
  return rows
 value=read(schema)
 if pos!=len(payload)or encode(schema,value)!=payload:raise ValueError('Housing trailing or changed native bytes')
 return value

def empty_layout():return([],[],[],0,-1)

def save_ack(layout,*,result=0):
 #3291290:result,full layout,existing furniture rewards,inventory delta,
 #placement set,bool,two current expansion/preset indexes. No economy reward.
 raw=struct.pack('>i',result)+encode(LAYOUT,layout)+bytes(4+4+4+1)+struct.pack('>ii',0,0)
 if len(raw)>MAX_BODY:raise ValueError('Housing936 bound')
 return Event(0x201,kind=0x936,payload=raw)
