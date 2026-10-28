"""Original2434D00 request50A/50C and241B370/241C030 native replies."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import record,empty_record
from els_server.domain.bag_capacity import wire_limit
from els_server.protocol.guild_bank_history_messages import text
NONE=2**64-1

def request(payload):
 if type(payload)is not bytes or len(payload)!=20:raise ValueError('Guild bank original transfer size')
 uid,count,target=struct.unpack('>QiQ',payload)
 if not 0<uid<2**63 or not 0<=count<=20000 or target!=NONE and not 0<target<2**63 or uid==target:raise ValueError('Guild bank native UID/count/target')
 return uid,count,target

def inventory(changes):
 rows=tuple(changes)
 if len({p for p,item in rows})!=len(rows)or any(p[0]not in(3,4,5,6)or not 0<=p[1]<wire_limit(p[0])for p,item in rows):raise ValueError('Guild bank current ordinary inventory changes')
 return struct.pack('>I',len(rows))+b''.join(record(item)if item else empty_record(*p)for p,item in rows)

def bank_map(items):
 items=tuple(items)
 if len(items)>1064 or len({i['uid']for i in items})!=len(items):raise ValueError('Guild bank original unique map')
 return struct.pack('>I',len(items))+b''.join(struct.pack('>Q',i['uid'])+record(i)for i in sorted(items,key=lambda i:i['uid']))

def deposited(items=(),changes=(),used=0,limit=0,*,result=0):
 # Last UID and string are constructor0/empty; only success current map and
 # inventory plus bank+3C/+40 counts are consumed by the ordinary path.
 return Event(0x201,kind=0x50b,payload=struct.pack('>i',result)+bank_map(items)+inventory(changes)+struct.pack('>Qii',0,max(0,limit-used),limit)+text(''))

def withdrawn(items=(),changes=(),used=0,limit=0,*,result=0):
 return Event(0x201,kind=0x50d,payload=struct.pack('>iii',result,max(0,limit-used),limit)+bank_map(items)+inventory(changes)+struct.pack('>Q',0)+text(''))

def overview(capacity,items,used,limit,*,result=0):
 return Event(0x201,kind=0x509,payload=struct.pack('>iQiiii',result,0,0,capacity,max(0,limit-used),limit)+empty_record(4,0)+bank_map(items)+struct.pack('>ii',0,0))
