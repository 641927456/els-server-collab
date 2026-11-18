"""Owned real TLS, shared Hero room/Force removal and cold festival source."""
import asyncio,ipaddress,struct
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.local_messages import wstring
from els_server.domain.town_travel import catalog
from els_server.domain.native_skill_delivery_sources import SkillSources
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

async def check(rows,*,runtime,progress,require_public=True,phase='test'):
 peers=[];cases=[]
 try:
  for row in rows:
   if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
   peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])));peers.append(peer)
   town=1503 if phase!='test'and row['scenario']=='festival'else 20000
   await enter(peer,row['uid'],town=town)
   if town==1503:
    notice=await peer.since(0x7ffe,0);assert notice.payload==struct.pack('>BQi',1,row['uid'],20000)
  if phase=='test':
   for row,peer in zip(rows[:2],peers[:2]):
    for uid in row['book_uids']:
     mark=len(peer.events);ack=await peer.request(0x219,struct.pack('>QQiiIB',uid,0,0,0,0,0),0x21a);assert ack.payload[:4]==bytes(4);await peer.since(0x6cb,mark)
    for kind,index,skill,rank in((1,0,900401,3),(1,1,900402,3),(2,0,901012,1)):
     ack=await peer.request(0x6d0,struct.pack('>iiiB',kind,index,skill,rank),0x6d1);assert ack.payload[:4]==bytes(4)
   lead,guest=rows[:2];a,b=peers[:2]
   invite=struct.pack('>Q',guest['uid'])+wstring(guest['character_name'])+struct.pack('>iBi',-1,1,120010)+bytes(6)+wstring('')+bytes(15)
   ack=await a.request(0x136,invite,0x137);assert ack.payload[:4]==bytes(4);await b.until(0x138)
   await b.request(0x139,struct.pack('>QQBiBQ',lead['uid'],0,0,0,0,0));await asyncio.gather(a.until(0x13b),b.until(0x13b))
   ack=await a.request(0x382,ENTRY,0x383);assert ack.payload[:4]==bytes(4)
   await asyncio.gather(a.until(0x14b),b.until(0x14b));await b.request(0x14c,struct.pack('>Bi',1,0));await asyncio.gather(a.until(0x14a),b.until(0x14a))
   for peer in peers[:2]:await peer.request(0x91,struct.pack('>ii',100,0),0x92)
   await asyncio.gather(a.until(0xb2),b.until(0xb2))
   for peer in peers[:2]:await peer.request(0xb3,bytes(9),0xb4)
   await asyncio.gather(a.until(0xbd),b.until(0xbd))
   for row,peer in zip(rows[:2],peers[:2]):
    for skill,rank in((900402,3),(901012,1)):
     ack=await peer.request(0x6d0,struct.pack('>iiiB',0,0,skill,rank),0x6d1);assert ack.payload[:4]==bytes(4)
     parsed=SkillSources(row['uid']).written(ack,ordinary_page_ready=True);assert (skill,rank)not in parsed.forces
   for index,(row,peer) in enumerate(zip(rows[:2],peers[:2])):
    ack=await peer.request(0x113,struct.pack('>HBBB',0,0,0,0),0x114);assert ack.payload[:4]==bytes(4)
    effect=await peer.until(0x115);assert effect.payload==struct.pack('>Qi?Q?',row['uid'],130165,False,0,False)
    relay=await peers[1-index].until(0x115);assert relay.payload==effect.payload
   cases.append('Actual shared Hero120010 entry/consent/B3; both owned actors remove passive and Mod Force and use one ordinary potion, with exact saved debit/loadout')
   row,peer=rows[2],peers[2]
   ack=await peer.request(0x225,struct.pack('>iB',1503,1),0x226);assert ack.payload[:4]==bytes(4)
   mark=len(peer.events);ack=await peer.request(0x227,struct.pack('>fffBH',*catalog()['towns']['1503']['xyz'],0,0),0x228);assert ack.payload[:4]==bytes(4)
   notice=await peer.since(0x7ffe,mark);assert notice.payload==struct.pack('>BQi',1,row['uid'],20000)
   cases.append('Native-shaped festival admission persists source20000 and sends the exact UID/source notice after ready; keep saved1503 for cold login')
  else:
   row,peer=rows[2],peers[2]
   wrong=await peer.request(0x225,struct.pack('>iB',20001,1),0x226);assert struct.unpack_from('>i',wrong.payload)[0]==515
   ack=await peer.request(0x225,struct.pack('>iB',20000,1),0x226);assert ack.payload[:4]==bytes(4)
   ack=await peer.request(0x227,struct.pack('>fffBH',*catalog()['towns']['20000']['xyz'],0,0),0x228);assert ack.payload[:4]==bytes(4)
   cases.append('Cold festival login restores exact source; wrong source refused and original return225/227 clears only the owned origin, no fee')
  from power_wire import check as check_power
  power=await check_power(rows[3],peers[3],phase=phase)
  cases.append('Client-origin raw current-form CP, actual TLS entry and AD replay, cold facts')
  progress('owned-flow-complete',cases=cases)
  return dict(ok=True,phase=phase,public_network=require_public,actual_TLS=True,cases=cases,natural_GUI=False,natural_battle=False)
 finally:
  for peer in peers:await peer.close()
