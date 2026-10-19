"""Replay all 21 source spawns through death, pickup, transitions and clear.

Checks explicit local fallback policy, not retail drop probability accuracy.
"""
import json,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_ground_loot import session,request,XYZ
from els_server.domain.dungeon_population import population
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]['payload'])
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'save.sqlite3';s=session(path);coins=[];food=[];visited=[]
 for stage_index in range(3):
  stage=population(stage_index)
  # Test every object, with the actual part-end object last.
  order=[n for n in stage['npcs'] if n['key']!=stage['clear_key']]+[stage['npcs'][stage['clear_key']]]
  for npc in order:
   data=bytearray(body);struct.pack_into('>i',data,0,npc['key'])
   struct.pack_into('>f',data,46,npc['hp']);struct.pack_into('>3f',data,33,*XYZ)
   event=Event(0x202,performers=(0,),kind=0xad,payload=bytes(data))
   before=set(s.world_drops);reply=s.handle(event)
   assert reply and reply[0].kind==0xae,(stage_index,npc)
   new=[s.world_drops[k] for k in set(s.world_drops)-before]
   visited.append((stage_index,npc['key']))
   if npc['template'] in (618,201,5):
    assert len(new)==1 and new[0]['template'] in (127000,127010)
    coins.append(new[0]['ed'])
   elif npc['template']==20:
    assert len(new)==1 and new[0]['template'] in (70000,70010,70020,70030,70040,70050)
    food.append(new[0]['template'])
   else:assert new==[],npc
   assert [e.kind for e in s.handle(event)]==[0xae]
   for drop in new:
    pickup=request(drop['template'],drop['drop_id'])
    assert [e.kind for e in s.handle(pickup)]==[0xd1,0xd2]
    assert [e.kind for e in s.handle(pickup)]==[0xd1]
   assert s.account.get_inventory_snapshot()['items']==[]
  reply=s.handle(Event(0x202,kind=0xbb,payload=b'\0'))
  if stage_index<2:
   assert [e.kind for e in reply]==[0xbc,0xb2]
   assert [e.kind for e in s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))]==[0xb4,0xb5,0xb6,0xb7,0xbd]
  else:assert [e.kind for e in reply]==[0xbc,0xd3,0xc1]
 assert len(visited)==21 and len(coins)==15 and sum(coins)==190 and len(food)==1
 saved=s.account.get_inventory_snapshot()
 assert saved['balances']['ed']==310 and saved['balances']['experience']==50
 assert [(i['template'],i['count']) for i in saved['items']]==[(77000,3)]
 assert LocalAccount(LocalState(path)).get_inventory_snapshot()==saved
 assert [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc]
 assert s.account.get_inventory_snapshot()==saved
print('PASS: all 21 El Tree spawns, 15 coins, one chest food, no gate loot, no fruit from mobs, transitions, pre-result inventory and durable once-only clear.')
