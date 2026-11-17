"""Original DE0590/2BDEF30 descriptor, DB DD20 accept, DB6E10 cold state."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader,wstring

def descriptor(name='',kind=1,*,proposer_class=0,proposer_side=-1,recipient_class=0,recipient_side=-1,selected=False):
 return wstring(name)+struct.pack('>BIHbHbB',0,kind,proposer_class,proposer_side,recipient_class,recipient_side,selected)
def read_descriptor(r):
 name=r.text(24)
 flag,kind,p_class,p_side,r_class,r_side,selected=(r.scalar(t)for t in('B','i','H','b','H','b','B'))
 if (flag or kind not in (1,7) or p_side not in (-1,0,1) or r_side not in (-1,0,1)
     or selected not in (0,1) or kind==1 and (p_class,p_side,r_class,r_side,selected)!=(0,-1,0,-1,0)):
  raise ValueError('Unsupported relationship descriptor')
 return name,dict(kind=kind,proposer_class=p_class,proposer_side=p_side,
                  recipient_class=r_class,recipient_side=r_side,selected=bool(selected))
def proposal(payload):
 r=Reader(payload);name,fields=read_descriptor(r);r.end()
 if not name:raise ValueError('Relationship target name')
 if fields['proposer_class'] or fields['recipient_class']:raise ValueError('Proposal classes come from the server')
 return name,fields
def propose_request(payload,*,with_kind=False):
 name,fields=proposal(payload)
 return (name,fields['kind']) if with_kind else name
def answer_request(payload):
 r=Reader(payload);answer=r.scalar('b');proposer=r.scalar('Q');name=r.text(24)
 opaque=(r.scalar('Q'),r.scalar('B'),r.scalar('H'));recipient=r.scalar('Q');own_name=r.text(24);flag=r.scalar('B');target_name,fields=read_descriptor(r);r.end()
 if answer not in(0,3,4,5,6)or opaque!=(0,0,0)or flag!=0 or not name or not own_name or target_name!=own_name:raise ValueError('Finite original couple answer')
 return dict(answer=answer,proposer=proposer,name=name,recipient=recipient,own_name=own_name,target_name=target_name,**fields)
def proposed(name,*,result=0,kind=1,**fields):return Event(0x201,kind=0x3fc,payload=struct.pack('>i',result)+wstring(name)+descriptor(name,kind,**fields))
def invitation(name,uid,target,*,kind=1,**fields):return Event(0x201,kind=0x3fd,payload=wstring(name)+struct.pack('>QB',uid,0)+descriptor(target,kind,**fields))
def answered(peer,anniversary=0,changes=(),*,answer=0,result=0,target_name='',kind=1,**fields):
 from els_server.domain.fashion_state import record,empty_record
 rows=list(changes);vector=struct.pack('>I',len(rows))+b''.join(empty_record(*p)if i is None else record(i)for p,i in rows)
 return Event(0x201,kind=0x3ff,payload=struct.pack('>ibQ',result,answer,peer['uid'])+wstring(peer['name'])+struct.pack('>Q',anniversary)+vector+descriptor(target_name,kind,**fields))
def cold(state):
 if state is None:return bytes(1)+bytes(8)+wstring('')*2+bytes(16)+bytes(1)+bytes(8)+bytes(3)
 # DB6E10 +5A reaches the client relationship object's +80, which the
 # original combat code uses for the 30-day benefit.
 return struct.pack('>bQ',state['kind'],state['peer_uid'])+wstring(state['peer_name'])+wstring('')+struct.pack('>QQ',state['created_at'],0)+bytes(1)+struct.pack('>Q',state.get('refreshed_at',0))+bytes(3)

def married(state):
 if state is None or state['kind']!=2:raise ValueError('Marriage notice requires a completed marriage')
 # D348D0 updates marriage/900 without starting a ceremony or refreshing it.
 return Event(0x201,kind=0x890,payload=bytes(2)+cold(state))

def visual_request(payload):
 r=Reader(payload);owner=r.scalar('Q');peer=r.scalar('Q');kind=r.scalar('i');words=r.text(1);r.end()
 if kind not in(2,3)or words!='':raise ValueError('Finite native current couple visual request')
 return owner,peer,kind
def visual(owner,peer,kind):
 if kind not in(2,3)or owner==peer:raise ValueError('Finite native couple visual')
 return Event(0x201,kind=0x403,payload=struct.pack('>QQi',owner,peer,kind)+wstring(''))


def farewell_request(payload):
 if type(payload)is not bytes or payload:raise ValueError('Original empty41A/41C body')

def farewell_quote(state=None,*,result=0):
 if result==0 and(state is None or state['kind']not in(1,2,7,8)or not state['peer_name']):raise ValueError('Quote requires current relationship and peer name')
 return Event(0x201,kind=0x41b,payload=struct.pack('>iQB',result,0,1 if result==0 else 0)+wstring(state['peer_name']if result==0 else''))

def farewell_ack(*,result=0):return Event(0x201,kind=0x41d,payload=struct.pack('>i',result))

def farewell_notice():return Event(0x201,kind=0x41e,payload=bytes(8))
