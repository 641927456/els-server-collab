"""Current challenge phase messages, pinned native party readers.

AE3/AE8: 2D7F750 / 2D58770. AE6: 2D7FA90. Its original reader
consumes challenge, phase, progress, member vector, deadline, result, actor,
and a UTF-16 string. An empty member vector is valid for local solo play.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring

def phase_ack(kind,result=0):
 if kind not in (0xae3,0xae8):raise ValueError('Unknown challenge acknowledgement')
 return Event(0x201,kind=kind,payload=struct.pack('>i',result)+wstring(''))

def phase_notice(challenge=-1,phase=-1,progress=0,deadline=0,*,result=0,actor=0,members=()):
 if (challenge,phase)!=(-1,-1) and (challenge,phase) not in ((4,1),(4,2),(4,3),(5,1),(5,2)):raise ValueError('Unknown challenge phase')
 if not 0<=progress<2**64 or not 0<=deadline<2**63 or not 0<=actor<2**64:raise ValueError('Challenge scalar bound')
 if len(members)>6 or len(set(members))!=len(members) or any(type(uid) is not int or not 1001<=uid<2**63 for uid in members):raise ValueError('Challenge member vector')
 return Event(0x201,kind=0xae6,payload=struct.pack('>iiQI',challenge,phase,progress,len(members))+b''.join(struct.pack('>Q',uid) for uid in members)+struct.pack('>QiQ',deadline,result,actor)+wstring(''))
