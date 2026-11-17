"""Original2435410 request526;241D5E0 reply527;241AB80 overview509."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.guild_coin_messages import changes_wire

def request(payload):
 if type(payload)is not bytes or len(payload)!=9:raise ValueError('Guild capacity native request length')
 uid,ticket=struct.unpack('>QB',payload)
 if ticket not in(0,1)or ticket==0 and uid!=0 or ticket==1 and not 0<uid<2**63:raise ValueError('Guild capacity original selector')
 return uid,ticket

def expanded(uid,balance,ticket,changes=(),*,result=0):
 if not 0<=balance<2**31 or ticket not in(0,1):raise ValueError('Guild capacity native balance/selector')
 # Original second int after UID has no consumer in241D5E0; constructor0.
 return Event(0x201,kind=0x527,payload=struct.pack('>iQii',result,uid,balance,0)+changes_wire(changes)+bytes((ticket,)))

def overview(capacity,*,result=0):
 # This pending implementation admits only an empty native bank. Transfer and
 # original scene admission must qualify before installation. No dummy items.
 from els_server.domain.fashion_state import empty_record
 if type(capacity)is not int or not 16<=capacity<=1064 or (capacity-16)%8:raise ValueError('Guild bank approved capacity')
 # i,Q,i,i,i,i,DB4F80 item,DB3490 UID-map,i,i. Original+38 reads capacity.
 return Event(0x201,kind=0x509,payload=struct.pack('>iQiiii',result,0,0,capacity,0,0)+empty_record(4,0)+struct.pack('>Iii',0,0,0))
