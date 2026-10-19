"""Script spawn roster boundaries, atomic batches and idempotent requests."""
import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_dungeon_routes import start,death
from els_server.domain.dungeon_npcs import resource_dto,encode_npc
from els_server.protocol.protocol_codec import Event

def request(s,templates,owner=2**64-1):
 rows=[]
 for template in templates:
  raw=bytearray.fromhex(s.dungeon_run.catalog._data['spawn_seed']);struct.pack_into('<ii',raw,0,-1,template);raw[0x3c]=1;raw[0x2c]=1
  dto=bytearray(resource_dto(raw));struct.pack_into('<Q',dto,0x6d,owner);rows.append(encode_npc(dto,0))
 return Event(0x202,kind=0x2ce,payload=struct.pack('>I',len(rows))+b''.join(rows))

class DungeonSpawnsTests(unittest.TestCase):
 def test_batch_creates_declared_minions_with_unique_reserved_slots(self):
  s,t=start(34030);before=set(s.dungeon_run.reserved_keys);e=request(s,[6103,6104])
  reply=s.handle(e,100);self.assertEqual([r.kind for r in reply],[0x2cf,0x2d0])
  new=[n for n in s.dungeon_run.current['npcs'] if n.get('dynamic')]
  self.assertEqual([n['template'] for n in new],[6103,6104]);self.assertFalse(before&{n['key'] for n in new})
  self.assertEqual(len({n['key'] for n in new}),2);self.assertTrue(all(n['no_drop'] for n in new))
  self.assertEqual([r.kind for r in s.handle(e,100)],[0x2cf]);self.assertEqual(len(s.dungeon_run.current['npcs']),len(before)+2)
  self.assertEqual(s.handle(request(s,[6105]),100)[0].payload,struct.pack('>i',-1))
  self.assertEqual(s.handle(death(new[0]))[0].kind,0xae);self.assertFalse(s.clear_notified)
  s.clear_notified=True
  self.assertEqual([(r.kind,r.payload) for r in s.handle(e,100)],[(0x2cf,bytes(4))])
  self.assertEqual(s.handle(request(s,[6105]),100)[0].payload,struct.pack('>i',-1))
  self.assertEqual(len([n for n in s.dungeon_run.current['npcs'] if n.get('dynamic')]),2)

 def test_unknown_template_foreign_creator_and_failed_batch_do_not_mutate(self):
  s,t=start(34030);before=list(s.dungeon_run.current['npcs'])
  for e in (request(s,[6101]),request(s,[6103],999999),request(s,[6103,999999])):
   self.assertEqual(s.handle(e,100)[0].payload,struct.pack('>i',-1));self.assertEqual(s.dungeon_run.current['npcs'],before)
  s.dungeon_substage_synced=False
  self.assertEqual(s.handle(request(s,[6103]),101)[0].payload,struct.pack('>i',-1))

 def test_capacity_and_completed_scene_do_not_spawn(self):
  s,t=start(34030);s.summon_keys=set(range(80));e=request(s,[6103])
  self.assertEqual(s.handle(e,100)[0].payload,struct.pack('>i',-1))
  s.summon_keys=set();s.clear_notified=True
  self.assertEqual(s.handle(e,101)[0].payload,struct.pack('>i',-1))

 def test_long_encounter_keeps_unique_ids_after_eighty_lifetime_spawns(self):
  s,t=start(34030);ids=[];e=request(s,[6103])
  for sequence in range(100,205):
   reply=s.handle(e,sequence);self.assertEqual([r.kind for r in reply],[0x2cf,0x2d0])
   npc=s.dungeon_run.current['npcs'][-1];ids.append(npc['key'])
   self.assertEqual(s.handle(death(npc))[0].kind,0xae)
  self.assertEqual(len(set(ids)),105);self.assertGreater(ids[-1],80)
  self.assertFalse(s.clear_notified);self.assertFalse(s.part_end_notified)
  old=next(n for n in s.dungeon_run.current['npcs'] if n['key']==ids[0])
  self.assertEqual([r.kind for r in s.handle(death(old))],[0xae])

if __name__=='__main__':unittest.main()
