"""Pinned DX11 C68/C69 modern synthesis: original native map and full reply."""
import struct
from els_server.domain.fashion_state import record,empty_record

def request(payload):
 if len(payload)<16:raise ValueError('Synthesis map size')
 count,=struct.unpack_from('>I',payload)
 if not 1<=count<=100 or len(payload)!=4+12*count:raise ValueError('Synthesis map bound')
 rows=[struct.unpack_from('>Qi',payload,4+12*n)for n in range(count)]
 if any(not 1<=uid<2**63 or not 1<=amount<=300 for uid,amount in rows)or len({uid for uid,_ in rows})!=count:raise ValueError('Synthesis instance/count')
 if rows!=sorted(rows):raise ValueError('Synthesis native ordered map')
 total=sum(amount for _,amount in rows)
 if not 3<=total<=300 or total%3:raise ValueError('Three materials per synthesis')
 return rows

def ack(ed=0,changes=(),rewards=None,result=0):
 rewards=rewards or {}
 if type(ed)is not int or not 0<=ed<2**63:raise ValueError('Synthesis ED')
 # BF33B0: result; C62740 map<int,int>; DD46E0 full item changes; Q ED.
 return(struct.pack('>iI',result,len(rewards))+b''.join(struct.pack('>ii',t,n)for t,n in sorted(rewards.items()))+
        struct.pack('>I',len(changes))+b''.join(record(i)if i else empty_record(*p)for p,i in changes)+struct.pack('>Q',ed))
