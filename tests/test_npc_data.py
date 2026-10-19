"""Native source identity, duplicate variants and live population references."""
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.game_data import client_data,CLIENT_SHA,DATA_DIR
from els_server.npc_data import NpcData
from els_server.domain.dungeon_population import population
from tools.build_npc_catalog import build

class NpcDataTests(unittest.TestCase):
 def test_catalog_and_runtime_population(self):
  data=client_data();self.assertEqual(data.npcs.manifest['count'],7526)
  self.assertEqual(data.npcs.manifest['registration_count'],7528)
  for stage in range(3):
   for spawn in population(stage)['npcs']:
    self.assertEqual(data.npc(spawn['template'])['enum'],spawn['source_group']['NPC_ID']['global'])
  self.assertEqual((data.npc(20)['class_id'],data.npc(20)['script'],data.npc(20)['is_npc']),(101,'Chest.lua',False))
  row=data.npc(20);row['variants'][0]['NPC_ID']=999
  self.assertEqual(data.npc(20)['variants'][0]['NPC_ID'],20)
  for identity in (-1,True,1.0,'20',99999999):
   with self.assertRaises(ValueError):data.npc(identity)
 def test_duplicates_are_not_silently_overwritten(self):
  for identity in (1694,1695):
   rows=client_data().npc(identity)['variants'];self.assertEqual(len(rows),2)
   self.assertNotEqual(rows[0]['MOTION'],rows[1]['MOTION'])
   self.assertEqual({k:v for k,v in rows[0].items() if k!='MOTION'},
                    {k:v for k,v in rows[1].items() if k!='MOTION'})
 def test_source_rebuild_and_tampering(self):
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d);built=build(dest)
   self.assertEqual((dest/'npcs.json').read_bytes(),(DATA_DIR/'npcs.json').read_bytes())
   self.assertEqual(built,client_data().npcs.manifest)
   NpcData(dest,CLIENT_SHA,built['enum_sha256'])
   with self.assertRaises(ValueError):NpcData(dest,'wrong-build',built['enum_sha256'])
   with self.assertRaises(ValueError):NpcData(dest,CLIENT_SHA,'wrong-enums')
   with (dest/'npcs.json').open('ab') as stream:stream.write(b' ')
   with self.assertRaises(ValueError):NpcData(dest,CLIENT_SHA,built['enum_sha256'])

if __name__=='__main__':unittest.main()
