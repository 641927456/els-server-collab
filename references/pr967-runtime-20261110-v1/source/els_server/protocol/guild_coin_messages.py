"""Original2351030 request524;2268F30 response525;2414E30 response523."""
import struct
from els_server.protocol.protocol_codec import Event
def changes_wire(changes):
 from els_server.domain.fashion_state import record,empty_record
 from els_server.domain.bag_capacity import wire_limit
 rows=list(changes);limit=wire_limit(4)
 if len(rows)>limit or len({tuple(p)for p,item in rows})!=len(rows)or any(p[0]!=4 or not 0<=p[1]<limit for p,item in rows):raise ValueError('Guild donation current native inventory positions')
 return struct.pack('>I',len(rows))+b''.join(empty_record(*p)if item is None else record(item)for p,item in rows)
def request(payload):
 if type(payload)is not bytes or len(payload)!=12:raise ValueError('Guild donation request length')
 uid,quantity=struct.unpack('>Qi',payload)
 if not 0<uid<2**63 or not 1<=quantity<=500:raise ValueError('Guild donation native UID/count')
 return uid,quantity
def donated(uid,quantity,balance,changes=(),*,result=0):
 if not 0<=balance<2**31:raise ValueError('Guild coin native signed balance')
 return Event(0x201,kind=0x525,payload=struct.pack('>iQii',result,uid,quantity,balance)+changes_wire(changes))
def balance_reply(balance,*,result=0):
 if not 0<=balance<2**31:raise ValueError('Guild coin native signed balance')
 # Existing version1 guilds have no emblem-point producer; original523 third int.
 return Event(0x201,kind=0x523,payload=struct.pack('>iii',result,balance,0))
