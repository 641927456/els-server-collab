"""Regression paths witnessed in the owned client on 2026-10-15."""
import json,sqlite3,struct,sys,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.domain.inventory_items import inventory_restore_map,item_body
from els_server.domain.reward_rules import should_drop
from els_server.domain.dungeon_population import population
from els_server.domain.character_stats import combat_attributes,combat_values
from els_server.protocol.local_messages import character_unit,player_initialization
from els_server.protocol.protocol_codec import Event

class Regressions(unittest.TestCase):
 def test_saved_inventory_map(self):
  rows=[dict(uid=12,template=77000,metadata=2,count=8,group=6,slot=0),
        dict(uid=11,template=274333,metadata=2,count=1,group=4,slot=0)]
  data=inventory_restore_map(rows)
  self.assertEqual(struct.unpack_from('>I',data)[0],2)
  for n,item in enumerate(reversed(rows)):
   key,uid,group,slot=struct.unpack_from('>QQBh',data,4+n*332)
   self.assertEqual((key,uid,group,slot),(item['uid'],item['uid'],item['group'],item['slot']))
   self.assertEqual(data[4+n*332+19:4+n*332+323],item_body(item))
  self.assertIn(data,player_initialization(items=rows).payload)
  self.assertTrue(player_initialization(items=rows).payload.endswith(bytes(30)))

 def test_actual_clear_end_then_town(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';account=LocalAccount(LocalState(path))
   s=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
   with closing(sqlite3.connect(path)) as db,db:
    db.execute('INSERT INTO inventory_items VALUES (1001001,1001,274333,2,1,4,0)')
    db.execute('INSERT INTO inventory_items VALUES (1001002,1001,77000,2,3,6,0)')
   snapshot=account.get_inventory_snapshot()
   s.role='game';s.phase='dungeon_active';s.clear_notified=True
   s.reward_receipt={'items':[i for i in snapshot['items'] if i['template']==77000]}
   end=Event(0x202,kind=0x67,payload=struct.pack('>i',0x72)+bytes(100))
   answer=s.handle(end)
   self.assertEqual([e.kind for e in answer],[0x68,0xd9])
   unit=character_unit(account.get_location(),True,account.get_skills(),snapshot['balances'],snapshot['items'])
   self.assertEqual(struct.unpack_from('>I',answer[1].payload,len(unit))[0],1)
   self.assertEqual(struct.unpack_from('>Q',answer[1].payload,len(unit)+4)[0],1001002)
   self.assertEqual([e.kind for e in s.handle(end)],[0x68])
   town=s.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
   self.assertEqual([e.kind for e in town],[0x226])
   ready=s.handle(Event(0x202,kind=0x227,payload=struct.pack('>3fBH',100.,100.,0.,0,0)))
   self.assertNotIn(0xd9,[e.kind for e in ready])
   self.assertEqual(s.phase,'town_ready')
   self.assertEqual(account.get_inventory_snapshot(),snapshot)

 def test_native_loot_flags_and_stable_rolls(self):
  run=str(uuid.UUID(int=1))
  for stage in range(3):
   p=population(stage)
   for n in p['npcs']:
    result=should_drop(30000,n,run,stage,p['clear_key'])
    self.assertEqual(result,should_drop(30000,n,run,stage,p['clear_key']))
    if n['no_drop'] or (not n['active'] and n['template']!=20):self.assertFalse(result)
  boss,chest=population(2)['npcs']
  self.assertFalse(should_drop(30000,boss,run,2,0))
  self.assertTrue(should_drop(30000,chest,run,2,0))
  mob=population(0)['npcs'][0]
  rolls=[should_drop(30000,mob,str(uuid.UUID(int=i+1)),0,6) for i in range(100)]
  self.assertFalse(any(rolls))  # No unsupported shared food pool on enemies.

 def test_wire_block_carries_the_worn_instance(self):
  c=dict(unit_class=5,unit_type=5,level=1)
  i=dict(uid=123,template=300994,metadata=0,count=1,group=9,slot=0)
  from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
  i['slot']=FASHION_EQUIP_SLOTS[i['template']]
  self.assertNotEqual(combat_values(c,[i]),combat_values(c))
  self.assertNotEqual(combat_attributes(c,[i]),combat_attributes(c))
  self.assertEqual(struct.unpack('>7f',combat_attributes(c,[i])),combat_values(c,[i],titles=False))
  self.assertEqual(len(combat_attributes(c,[i])),28)

 def test_inactive_chest_spawns_once_without_advancing_clear(self):
  with tempfile.TemporaryDirectory() as d:
   s=LocalSession(LocalAccount(LocalState(Path(d)/'save.sqlite3')),enter_town=True,enter_dungeon=True,
       client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,
       clear_test=True,reward_test=True,item_test=True,drop_probe=True,drop_test=True)
   s.role='game';s.phase='dungeon_active';s.gate_stage=2;s.dungeon_substage_synced=True;s.reward_run_id=str(uuid.uuid4())
   source=json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]['payload']
   body=bytearray.fromhex(source);struct.pack_into('>i',body,0,1);struct.pack_into('>f',body,46,1000)
   event=Event(0x202,performers=(0,),kind=0xad,payload=bytes(body))
   self.assertEqual([e.kind for e in s.handle(event)],[0xae,0xaf,0xcf])
   self.assertFalse(s.part_end_notified);self.assertFalse(s.clear_notified)
   self.assertEqual(len(s.world_drops),1)
   self.assertEqual([e.kind for e in s.handle(event)],[0xae])
   self.assertEqual(len(s.world_drops),1)

if __name__=='__main__':unittest.main()
