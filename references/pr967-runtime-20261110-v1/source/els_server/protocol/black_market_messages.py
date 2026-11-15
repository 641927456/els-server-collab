"""Current original D3B..D49 black-market DTOs; no client additions."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

def event(kind,payload):return Event(0x201,kind=kind,payload=payload)
def result(kind,code=0):
 if kind not in(0xd3c,0xd3e,0xd3f,0xd41,0xd48)or type(code)is not int:raise ValueError('Market result identity')
 return event(kind,struct.pack('>i',code))
def tickets(count,start,end):
 if type(count)is not int or not 0<=count<=2 or not 0<=start<=end<2**63:raise ValueError('Market ticket snapshot')
 return event(0xd49,struct.pack('>iQQ',count,start,end))
def availability(opened,deadline):
 if type(opened)is not bool or type(deadline)is not int or not 0<=deadline<2**63:raise ValueError('Market opening snapshot')
 return event(0xd3a,struct.pack('>?Q',opened,deadline))
def member(p):
 # Original2C2D950/DB93D0: Q,Q,Q,i,H,enum32,wstring,bool.
 return struct.pack('>QQQiHI',p['account'],p.get('guild',0),p['uid'],p['level'],p['unit_type'],p['unit_class'])+wstring(p['name'])+bytes(1)
def roster(people):
 if not 1<=len(people)<=11 or len({p['uid']for p in people})!=len(people):raise ValueError('Market actual roster')
 return event(0xd40,struct.pack('>I',len(people))+b''.join(member(p)for p in people))
def lot_fields(lot,index,total,deadline):
 return struct.pack('>iiiiQiQQQ',total,index,lot['template'],lot['quantity'],lot['opening'],lot['tier'],lot.get('winner',0),lot.get('price',0),deadline)
def lot(l,index,total,deadline):return event(0xd42,lot_fields(l,index,total,deadline))
def balance(ed,revision,code=None):
 if type(ed)is not int or not 0<=ed<2**63 or type(revision)is not int or not 0<=revision<2**31:raise ValueError('Market ED snapshot')
 return event(0xd45 if code is None else 0xd44,(b''if code is None else struct.pack('>i',code))+struct.pack('>Qi',ed,revision))
def finished(l,index,total,dividend,next_time,history,people):
 # D46 is a distinct DTO: its2C Q is dividend,34 Q is next deadline.
 payload=lot_fields(l,index,total,dividend)+struct.pack('>QI',next_time,len(history))
 by_uid={p['uid']:p for p in people}
 for h in history:
  winner=h.get('winner',0);p=by_uid.get(winner)
  # Original result vector2C2DD40: index, native item tuple, native member, bid.
  payload+=struct.pack('>iiiQi',h['index'],h['template'],h['quantity'],h['opening'],h['tier'])
  payload+=member(p)if p is not None else struct.pack('>QQQiHI',0,0,0,0,0,0)+wstring('')+bytes(1)
  payload+=struct.pack('>Q',h.get('price',0))
 return event(0xd46,payload)
def request(kind,payload,uid):
 if not isinstance(payload,bytes):raise ValueError('Market request bytes')
 if kind in(0xd3b,0xd3d):
  if payload:raise ValueError('Market original empty matching request')
  return None
 if kind==0xd43:
  if len(payload)!=16:raise ValueError('Market native bid size')
  actor,ed=struct.unpack('>QQ',payload)
  if actor!=uid or not 0<ed<2**63:raise ValueError('Market native bid owner/ED')
  return ed
 if kind==0xd47:
  if payload!=bytes(12):raise ValueError('Market original UI-close defaults')
  return None
 raise ValueError('Market native request kind')
