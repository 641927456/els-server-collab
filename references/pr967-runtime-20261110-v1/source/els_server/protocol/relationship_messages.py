"""Original DE0590/2BDEF30 descriptor, DB DD20 accept, DB6E10 cold state."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader,wstring

def descriptor(name='',kind=1):return wstring(name)+struct.pack('>BIHbHbB',0,kind,0,-1,0,-1,0)
def read_descriptor(r):
 name=r.text(24);fields=tuple(r.scalar(t)for t in('B','i','H','b','H','b','B'))
 if fields!=(0,1,0,-1,0,-1,0):raise ValueError('Finite original couple descriptor')
 return name
def propose_request(payload):
 r=Reader(payload);name=read_descriptor(r);r.end()
 if not name:raise ValueError('Couple target name')
 return name
def answer_request(payload):
 r=Reader(payload);answer=r.scalar('b');proposer=r.scalar('Q');name=r.text(24)
 opaque=(r.scalar('Q'),r.scalar('B'),r.scalar('H'));recipient=r.scalar('Q');own_name=r.text(24);flag=r.scalar('B');target_name=read_descriptor(r);r.end()
 if answer not in(0,3,4,5,6)or opaque!=(0,0,0)or flag!=0 or not name or not own_name or target_name!=own_name:raise ValueError('Finite original couple answer')
 return dict(answer=answer,proposer=proposer,name=name,recipient=recipient,own_name=own_name,target_name=target_name)
def proposed(name,*,result=0):return Event(0x201,kind=0x3fc,payload=struct.pack('>i',result)+wstring(name)+descriptor(name))
def invitation(name,uid,target):return Event(0x201,kind=0x3fd,payload=wstring(name)+struct.pack('>QB',uid,0)+descriptor(target))
def answered(peer,anniversary=0,changes=(),*,answer=0,result=0,target_name=''):
 from els_server.domain.fashion_state import record,empty_record
 rows=list(changes);vector=struct.pack('>I',len(rows))+b''.join(empty_record(*p)if i is None else record(i)for p,i in rows)
 return Event(0x201,kind=0x3ff,payload=struct.pack('>ibQ',result,answer,peer['uid'])+wstring(peer['name'])+struct.pack('>Q',anniversary)+vector+descriptor(target_name))
def cold(state):
 if state is None:return bytes(1)+bytes(8)+wstring('')*2+bytes(16)+bytes(1)+bytes(8)+bytes(3)
 # Original1385780 restores type/partner/name and anniversary from DB6E10.
 # No unsourced titles, rewards, marriage counters or love words are added.
 return struct.pack('>bQ',1,state['peer_uid'])+wstring(state['peer_name'])+wstring('')+struct.pack('>QQ',state['created_at'],0)+bytes(1)+bytes(8)+bytes(3)

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
 if result==0 and(state is None or state['kind']!=1 or not state['peer_name']):raise ValueError('Quote requires actual couple1 and peer name')
 return Event(0x201,kind=0x41b,payload=struct.pack('>iQB',result,0,1 if result==0 else 0)+wstring(state['peer_name']if result==0 else''))

def farewell_ack(*,result=0):return Event(0x201,kind=0x41d,payload=struct.pack('>i',result))

def farewell_notice():return Event(0x201,kind=0x41e,payload=bytes(8))
