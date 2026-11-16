import ipaddress,struct
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.domain.el_search_collection import entry
from els_server.storage.collection_synergy import slots_wire
from els_server.protocol.el_search_collection_messages import notice
from els_server.domain.first_story_entry import MAPS
from els_server.protocol.local_messages import wstring
def tutorial_room(unit):
 schema=((0,'B'),(1,'Q'),(9,'I'),(0xd,'s'),(0x2d,'B'),(0x2e,'B'),(0x2f,'B'),(0x30,'s'),(0x50,'B'),(0x51,'B'),(0x52,'s'),(0x72,'H'),(0x74,'s'),(0x94,'B'),(0x95,'B'),(0x96,'B'),(0x97,'i'),(0x9b,'B'),(0x9c,'B'),(0x9d,'f'),(0xa1,'H'),(0xa3,'H'),(0xa5,'Q'),(0xad,'i'),(0xb1,'B'),(0xb2,'i'),(0xb6,'B'),(0xb7,'B'),(0xb8,'Q'),(0xc0,'Q'),(0xc8,'i'),(0xcc,'B'))
 values={0:1,0xd:'tutorial',0x50:1,0xb2:MAPS[unit]}
 wire=b''.join(wstring(values.get(offset,''))if fmt=='s'else struct.pack('>'+fmt,values.get(offset,0))for offset,fmt in schema)+bytes(4)
 for _,fmt in((0xdd,'B'),(0xde,'B'),(0xdf,'i'),(0xe3,'B'),(0xe4,'B'),(0xe5,'Q')):wire+=struct.pack('>'+fmt,0)
 wire+=bytes(4)
 for _,fmt in((0xfd,'B'),(0xfe,'i'),(0x102,'Q'),(0x10a,'Q')):wire+=struct.pack('>'+fmt,0)
 return wire
async def check(rows,*,runtime,progress,require_public=True,phase='test'):
 peers=[];cases=[]
 try:
  for row in rows:
   if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
   peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])));peers.append(peer)
   if row['scenario']!='tutorial':await enter(peer,row['uid'])
   else:
    for kind,response in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488),(0x490,0x491)):await peer.request(kind,response=response)
    for kind,body,response in((0x28,struct.pack('>Q',row['uid']),0x29),(0x6e9,b'',0x6ea),(0x5bf,bytes(8),0x5c0),(0x32,b'',0x33)):
     selected=await peer.request(kind,body,response);assert selected.payload[:4]==bytes(4)
  if phase=='test':
   for row,peer in zip(rows,peers):
    if row['scenario']=='Noah':
     await peer.request(0x80d,struct.pack('>i',1),0x80e)
     mark=len(peer.events);reply=await peer.request(0x80f,struct.pack('>IIH',1,1200314630,1),0x810);assert reply.payload[:4]==bytes(4)
     await peer.since(0x55b,mark)
     refusal=await peer.request(0x80f,struct.pack('>IIH',1,1200288319,1),0x810);assert struct.unpack_from('>i',refusal.payload)[0]==151
     cases.append('35-level Noah ordinary second-class change succeeds for 50 ED; under-level transcendence retains legal refusal 151')
    elif row['scenario']=='tutorial':
     progress('tutorial-entry-before-room')
     await peer.request(0x60,tutorial_room(15),0x61)
     loaded=await peer.request(0x91,struct.pack('>ii',100,0),0x92);assert loaded.payload[:4]==bytes(4)
     synchronized=await peer.request(0xb3,bytes(9),0xb4);assert synchronized.payload[:4]==bytes(4)
     await peer.request(0x3be,bytes(5))
     following=await peer.request(0x91,struct.pack('>ii',100,0),0x92);assert following.payload[:4]==bytes(4)
     cases.append('Fresh owned-account Lithia admits tutorial/shared lifecycle, consumes encrypted battle report and delivers the next progress request without disconnect')
    else:
     accepted=await peer.request(0xee,struct.pack('>ii',52700,10025),0xef);assert accepted.payload[:4]==bytes(4)
     claimed=await peer.request(0xf4,struct.pack('>iiI5B',52700,0,0,0,0,1,1,0),0xf5);assert claimed.payload[:4]==bytes(4)
     selected=await peer.request(0x960,slots_wire({1:(1,1)})+struct.pack('>i',1),0x961);assert selected.payload[:4]==bytes(4)
     for item,target in zip(row['item_uids'],row['targets']):
      mark=len(peer.events);reply=await peer.request(0x219,struct.pack('>QQiiIB',item,0,0,0,0,0),0x21a);assert reply.payload[:4]==bytes(4)
      update=await peer.since(0x955,mark)
      expected=dict(active=True,registered=[entry(target,1)],expiry=0,expansion=0,presets={1:{}},field1d=1,field21=1)
      assert update.payload==notice(expected).payload
     cases.append('Finite52700 opens for 500 EP; two real 219 career changes replace 955 with only current contribution and remove unsupported synergy')
  else:cases.append('Both final careers, exact ED/EP and current collection state restored on cold login')
  progress('public-requests-complete-awaiting-cold-read',cases=cases)
  return dict(ok=True,phase=phase,public_network=require_public,actual_TLS=True,cases=cases,natural_GUI=False,natural_battle=False)
 finally:
  for peer in peers:await peer.close()
