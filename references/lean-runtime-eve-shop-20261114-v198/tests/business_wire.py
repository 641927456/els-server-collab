import ipaddress,struct
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig
async def check(rows,*,runtime,progress,require_public=True,phase='test'):
 peers=[];cases=[]
 try:
  for row in rows:
   if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
   peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])));peers.append(peer);await enter(peer,row['uid'])
  if phase=='test':
   for row,peer in zip(rows,peers):
    catalog=await peer.request(0x80d,struct.pack('>i',1),0x80e)
    count,=struct.unpack_from('>I',catalog.payload,1);assert len(catalog.payload)==5+28*count
    templates={struct.unpack_from('>Iiiiiii',catalog.payload,5+28*i)[1]for i in range(count)}
    assert {217970,217980}.issubset(templates)
    for template in (row['first'],row['second']):
     mark=len(peer.events);reply=await peer.request(0x80f,struct.pack('>IIH',1,1200000000+template,1),0x810)
     assert reply.payload[:4]==bytes(4)
     await peer.since(0x55b,mark)
     kinds=[e.kind for e in peer.events[mark:]]
     assert kinds.index(0x810)<kinds.index(0x29f)<kinds.index(0x131)<kinds.index(0x55b)
    rejection=await peer.request(0x80f,struct.pack('>IIH',1,1200000000+row['second'],1),0x810)
    assert rejection.payload[:4]!=bytes(4)
    cases.append('Eve ordinary first job and '+str(row['target'])+' second job: two 50 ED purchases, native career/skill notices, duplicate new operation rejected')
  else:cases.append('Both Eve careers and exact 900 ED cold login after completed public purchases')
  progress('public-requests-complete-awaiting-cold-read',cases=cases)
  return dict(ok=True,phase=phase,public_network=require_public,actual_TLS=True,cases=cases,natural_GUI=False,natural_battle=False)
 finally:
  for peer in peers:await peer.close()
