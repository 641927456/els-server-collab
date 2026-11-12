"""Complete original224 for the five source-qualified Feta rows only."""
import struct
from els_server.domain.fashion_state import record,empty_record

def acknowledgement(ed,changes=(),rewards=(),*,result=0,exchange_type=3):
 if type(ed)is not int or not 0<=ed<2**63 or type(result)is not int or result not in(0,-1)or exchange_type not in(1,3):raise ValueError('Feta224 scalar')
 if type(changes)not in(list,tuple)or len(changes)>72 or type(rewards)not in(list,tuple):raise ValueError('Feta224 collection')
 allowed={(119217,1),(119218,1),(119219,1),(119220,1),(119323,1),(710313,20),(710193,20),(119328,1),(30880,1),(119216,4)}
 if(result==-1 and(changes or rewards))or(result==0 and(len(rewards)>1 or rewards and tuple(rewards[0])not in allowed)):raise ValueError('Feta224 exact reward profile')
 seen=set();uids=set();body=[]
 for position,item in changes:
  if(type(position)is not tuple or len(position)!=2 or any(type(v)is not int for v in position)
     or not 0<=position[0]<=255 or not 0<=position[1]<=32767 or position in seen):raise ValueError('Feta224 changed position')
  seen.add(position)
  if item is None:body.append(empty_record(*position))
  else:
   if(item['group'],item['slot'])!=position or item['uid']in uids:raise ValueError('Feta224 item identity')
   uids.add(item['uid']);body.append(record(item))
 return(struct.pack('>iI',result,len(body))+b''.join(body)+struct.pack('>I',len(rewards))
  +b''.join(struct.pack('>ii',*r)for r in rewards)+struct.pack('>BBQQ',1,exchange_type,0,ed))
