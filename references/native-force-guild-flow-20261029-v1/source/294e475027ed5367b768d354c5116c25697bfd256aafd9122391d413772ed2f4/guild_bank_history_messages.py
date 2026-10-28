"""2435090 original50E,241CE60/DDA320 original50F history records."""
from datetime import datetime,timezone,timedelta
import struct
from els_server.protocol.protocol_codec import Event
FIELDS=frozenset(('owner','unit_class','level','direction','grade','name','template','quantity','enhancement','created_at','stage'))
def text(value):
 if type(value)is not str or '\0'in value:raise ValueError('Guild history native string')
 raw=value.encode('utf-16le')
 if len(raw)>8192:raise ValueError('Guild history string bound')
 return struct.pack('>I',len(raw))+raw
def request(payload):
 if type(payload)is not bytes or len(payload)!=5:raise ValueError('Guild history original request length')
 page,tab=struct.unpack('>IB',payload)
 if not 1<=page<2**31 or tab not in(0,1,2):raise ValueError('Guild history current page/filter')
 return page,tab
def record(row):
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES
 if type(row)is not dict or set(row)!=FIELDS:raise ValueError('Guild history exact plain record')
 if any(type(row[k])is not int for k in FIELDS-{'name'}):raise ValueError('Guild history record types')
 if(not 0<row['owner']<2**63 or not 0<row['unit_class']<2**16 or not 1<=row['level']<=99 or row['direction']not in(0,1)or row['grade']not in(1,6)or row['template']not in VERIFIED_TEMPLATES or not 1<=row['quantity']<=20000 or row['enhancement']!=0 or not 0<row['created_at']<2**63 or row['stage']not in(0,1,2)):raise ValueError('Guild history finite coin record')
 stamp=datetime.fromtimestamp(row['created_at'],timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
 # Original0x7D row: actorQ/classH/leveli/in-outB/gradeB/name;
 # templatei/counti/enhancementB/time; empty option vector; career stagei;
 # normal item name-variant constructor fields0/0. No equipment-log admission.
 return(struct.pack('>QHiBB',row['owner'],row['unit_class'],row['level'],row['direction'],row['grade'])+text(row['name'])+struct.pack('>iiB',row['template'],row['quantity'],0)+text(stamp)+struct.pack('>Iiii',0,row['stage'],0,0))
def reply(page,pages,tab,rows=(),*,result=0):
 rows=tuple(rows)
 if len(rows)>10 or not 1<=page<=pages<2**31 or tab not in(0,1,2):raise ValueError('Guild history pagination')
 return Event(0x201,kind=0x50f,payload=struct.pack('>iIIBI',result,page,pages,tab,len(rows))+b''.join(record(r)for r in rows))
