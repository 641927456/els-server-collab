"""Current native A08 candidates and complete A09; SQL selects real listing identity.

Variant decoding never authorizes a purchase. The caller must select exactly one
candidate matching a current authoritative listing and its exact template, or
reject; a durable original receipt is required for replay after listing removal.
"""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.domain.bag_capacity import BAG_GROUPS,wire_limit
from els_server.domain.fashion_state import record,empty_record

def _changes_wire(changes):
 if not isinstance(changes,(list,tuple))or len(changes)>sum(wire_limit(g)for g in BAG_GROUPS):raise ValueError('TradeBoard changed-record bound')
 positions=set();identities=set();rows=[]
 for pos,item in changes:
  if(type(pos)not in(list,tuple)or len(pos)!=2 or any(type(v)is not int for v in pos)
     or pos[0]not in BAG_GROUPS or not 0<=pos[1]<wire_limit(pos[0])or tuple(pos)in positions):raise ValueError('TradeBoard original bag record position')
  positions.add(tuple(pos))
  if item is not None:
   if(item.get('group'),item.get('slot'))!=tuple(pos)or item.get('uid')in identities:raise ValueError('TradeBoard changed UID/position')
   identities.add(item['uid']);rows.append(record(item))
  else:rows.append(empty_record(*pos))
 return struct.pack('>I',len(rows))+b''.join(rows),identities

def _id(value):
 if type(value)is not int or not 0<value<2**63:raise ValueError('TradeBoard exact identity')
 return value

def sale_request(payload):
 if type(payload)is not bytes or len(payload)!=32:raise ValueError('TradeBoard original A04 length')
 uid,template,count,price,aux_uid=struct.unpack('>QiiQQ',payload);_id(uid)
 if not 0<template<2**31 or not 0<count<2**31 or not 1<=price<=10_000_000_000 or not 0<=aux_uid<2**63:raise ValueError('TradeBoard A04 scalar range')
 return uid,template,count,price,aux_uid

def cancel_request(payload):
 if type(payload)is not bytes or len(payload)!=9:raise ValueError('TradeBoard original 9FC length')
 flag,identity=struct.unpack('>BQ',payload)
 if flag!=1:raise ValueError('TradeBoard unsupported cancel mode')
 return _id(identity)

def pickup_request(payload):
 if type(payload)is not bytes or len(payload)!=9:raise ValueError('TradeBoard original A06 length')
 identity,resell=struct.unpack('>QB',payload);_id(identity)
 if resell not in(0,1):raise ValueError('TradeBoard original resell boolean')
 return identity,bool(resell)

def own_rows_wire(rows):
 """467 own-list rows, distinct from the 44D public offers.

 Q8/Q10/Q39/Q51/B5E are neutral compatibility fields; current qualified
 own-list, rendering and re-list consumers only copy them. No money or
 entitlement is authorized by these fields.
 """
 from els_server.domain.inventory_items import fixture
 if type(rows)not in(list,tuple)or len(rows)>30:raise ValueError('TradeBoard own-list row bound')
 result=[];seen=set()
 count_offset=next(f['wire_offset']for f in fixture()['fields']if int(f['offset'],0)==5)
 for r in rows:
  identity=_id(r['id'])
  if identity in seen:raise ValueError('TradeBoard duplicate own listing')
  seen.add(identity);remaining=r['remaining'];sold=r['sold_count']
  if(type(remaining)is not int or type(sold)is not int or not 0<=remaining<2**31 or not 0<=sold<2**31
     or r['view_state']not in(1,2)or r.get('vip_type',1)!=1):raise ValueError('TradeBoard own-list source scalar')
  item=bytearray(record(dict(r['item'],count=max(remaining,1))))
  struct.pack_into('>i',item,11+count_offset,remaining)
  result.append(struct.pack('>QQQ',identity,0,0)+wstring(r['seller_name'])+
   struct.pack('>BQQQQiBB',r['view_state'],0,r['expires_at'],r['unit_price'],0,sold,1,0)+item)
 return struct.pack('>I',len(result))+b''.join(result)

def _response(kind,payload,text):
 if type(text)is not str or len(text.encode('utf-16le'))>4096:raise ValueError('TradeBoard response text bound')
 payload+=wstring(text)
 if len(payload)+64>1024*1024:raise ValueError('TradeBoard response frame bound')
 return Event(0x201,kind=kind,payload=payload)

def own_ack(rows=(),*,result=0,text=''):
 return _response(0xa03,struct.pack('>iB',result,1)+own_rows_wire(rows),text)

def sale_ack(ed=0,changes=(),rows=(),*,result=0,text=''):
 vector,_=_changes_wire(changes)
 return _response(0xa05,struct.pack('>iQQ',result,ed,0)+vector+own_rows_wire(rows),text)

def cancel_ack(identity,rows=(),*,result=0,text=''):
 if not(result and identity==0):_id(identity)
 return _response(0x9fd,struct.pack('>iBQ',result,1,identity)+own_rows_wire(rows),text)

def pickup_ack(identity,ed=0,changes=(),rows=(),resell=False,*,result=0,text=''):
 if type(resell)is not bool:raise ValueError('TradeBoard resell flag')
 vector,_=_changes_wire(changes)
 if not(result and identity==0):_id(identity)
 return _response(0xa07,struct.pack('>iQQ',result,identity,ed)+own_rows_wire(rows)+vector+struct.pack('>?',resell),text)

@functools.lru_cache(maxsize=1)
def variants():
 raw=(PROJECT_ROOT/'els_server/data/trade_board_purchase_variants.json').read_bytes()
 doc=json.loads(raw)
 if(hashlib.sha256(raw).hexdigest()!='02375a369e8a4fa5fc9477c592e5b62636585ac32b6bfdb73e3f5f970bdb3bc6'
    or doc['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
    or doc['grammar_evidence_sha256']!='049883dd68c30a6a3d659ca068e1276f7de08ec7e6438b15ab31d3ffcb0683c8'
    or [r['variant']for r in doc['variants']]!=list(range(20))):raise ValueError('TradeBoard exact native variants')
 for row in doc['variants']:
  fields=row['fields']
  if(sorted(f['field']for f in fields)!=['listing_id','noise','quantity','template']
     or sorted(f['kind']for f in fields)!=['noise','u32','u32','u64']):raise ValueError('TradeBoard native variant field contract')
 return doc['variants']

def purchase_candidates(payload):
 """Bounded native decoding, returning possibilities rather than client authority."""
 if type(payload)is not bytes or not 24<=len(payload)<=36:raise ValueError('TradeBoard native purchase length')
 matches=set()
 for grammar in variants():
  pos=0;out={}
  try:
   for field in grammar['fields']:
    if field['kind']=='noise':
     if pos+4>len(payload):raise ValueError('TradeBoard truncated noise')
     count=struct.unpack_from('>I',payload,pos)[0]
     if not 4<=count<=16 or pos+4+count>len(payload):raise ValueError('TradeBoard noise bound')
     pos+=4+count
    else:
     size=8 if field['kind']=='u64'else 4
     if pos+size>len(payload):raise ValueError('TradeBoard truncated field')
     value=int.from_bytes(payload[pos:pos+size],'big')^int(field['mask'],0)
     out[field['field']]=value;pos+=size
   if(pos!=len(payload)or not 0<out['listing_id']<2**63 or not 0<out['template']<2**31
      or not 0<out['quantity']<2**31):continue
   matches.add((out['listing_id'],out['template'],out['quantity']))
  except(ValueError,struct.error):continue
 if not matches:raise ValueError('Unknown native TradeBoard purchase')
 return tuple(sorted(matches))

def purchase_ack(ed=0,changes=(),listing_id=0,remaining=0,*,result=0,text=''):
 if(type(ed)is not int or not 0<=ed<=70_000_000_000
    or type(listing_id)is not int or not 0<=listing_id<2**63
    or type(remaining)is not int or not 0<=remaining<2**31
    or type(result)is not int or not -2**31<=result<2**31
    or type(text)is not str or len(text.encode('utf-16le'))>4096):raise ValueError('TradeBoard purchase response bounds')
 if not result and not listing_id:raise ValueError('Successful purchase requires original listing identity')
 if result and(changes or listing_id or remaining):raise ValueError('Rejected TradeBoard purchase has no item/listing mutations')
 vector,_=_changes_wire(changes)
 payload=struct.pack('>iQ',result,ed)+vector+struct.pack('>Qi',listing_id,remaining)+wstring(text)
 if len(payload)+64>1024*1024:raise ValueError('TradeBoard response frame bound')
 return Event(0x201,kind=0xa09,payload=payload)
