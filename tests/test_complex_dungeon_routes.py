"""Regression for current complex source fields and internal challenge scope."""
import json,struct,sys,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from els_server.domain.dungeon_routes import DungeonRun,route_catalog
from test_dungeon_routes import start,death,finish
from els_server.protocol.protocol_codec import Event

class ComplexDungeonRoutesTests(unittest.TestCase):
 def test_friendly_ignia_does_not_block_kill_all(self):
  s,t=start(33302);run=s.dungeon_run
  friendly=[n for n in run.current['npcs'] if n.get('team')==0]
  self.assertTrue(friendly);self.assertTrue(all(n['ally'] for n in friendly))
  for n in run.current['npcs']:
   if n.get('team')!=0:s.handle(death(n))
  self.assertTrue(any(run.condition_ready(c) for c in run.current['conditions']))
  self.assertTrue(all(n['key'] not in run.defeated for n in friendly))

 def test_source_fraction_uses_original_integer_conversion(self):
  for identity in (33881,120000,120010):
   run=DungeonRun(identity,str(uuid.uuid4()));found=[]
   for stage in run.graph['stages']:
    run._load_stage(int(stage))
    found += [n for p in run.parts.values() for n in p['npcs'] if n['source_key_code']==2.5]
   self.assertTrue(found,identity);self.assertTrue(all(n['key_code']==2 for n in found))

 def test_internal_nodes_have_no_standalone_admission(self):
  cat=route_catalog();s,_=start(33302);s.phase='town_ready'
  self.assertEqual(len(cat._data['internal_routes']),18)
  for value in cat._data['internal_routes']:
   identity=int(value)
   self.assertFalse(cat.supports(identity));self.assertTrue(cat.supports(identity,internal=True))
   with self.assertRaises(ValueError):DungeonRun(identity,str(uuid.uuid4()))
   run=DungeonRun(identity,str(uuid.uuid4()),internal=True)
   self.assertEqual(struct.unpack_from('>i',run.population_event().payload)[0],0)
   self.assertEqual(s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,identity)))[0].payload[:4],struct.pack('>i',817))

 def test_challenge_nodes_match_current_scope_and_source_counts(self):
  cat=route_catalog();phases=cat._data['challenges']
  self.assertEqual([(p['challenge'],p['phase']) for p in phases],[(4,1),(4,2),(4,3),(5,1),(5,2)])
  self.assertEqual({str(n['dungeon']) for p in phases for n in p['nodes']},set(cat._data['internal_routes']))
  first=phases[0]
  self.assertEqual([(n['count'],n['flag'],n['requires']) for n in first['nodes']],[(1,0,0),(1,1,0),(2,2,3),(1,4,15)])
  self.assertEqual([p['seconds'] for p in phases],[3600,3600,7200,5400,7200])

 def test_original_seventeen_settle_return_and_reenter(self):
  pending=json.loads((ROOT/'analysis/complex-dungeons-20261015/baseline/dungeon_routes.manifest.json').read_text())['unsupported']
  self.assertEqual(len(pending),17)
  for identity in map(int,pending):
   with self.subTest(dungeon=identity),tempfile.TemporaryDirectory() as d:
    path=Path(d)/'save.sqlite3';s,t=start(identity,path);old=s.reward_run_id
    finish(s,t);self.assertFalse(getattr(s,'dungeon_failed',False))
    self.assertEqual(s.account.get_reward_balances()['ed'],120)
    self.assertEqual(s.handle(Event(0x202,kind=0x225,payload=struct.pack('>iB',s.account.get_location()['map'],0)))[-1].kind,0x226)
    s2,t2=start(identity,path);self.assertNotEqual(s2.reward_run_id,old);finish(s2,t2)
    self.assertEqual(s2.account.get_reward_balances()['ed'],240)

 def test_defence_friendly_gate_death_is_no_reward_failure(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s,t=start(38300,path)
   gate=next(n for n in s.dungeon_run.current['npcs'] if n['template']==1368)
   event=death(gate);reply=s.handle(event)
   self.assertEqual([e.kind for e in reply],[0xae,0xaf,0xc1]);self.assertEqual(reply[-1].payload[16],0)
   self.assertTrue(s.dungeon_failed);self.assertIsNone(s.reward_receipt)
   self.assertEqual(s.account.get_reward_balances()['ed'],0)
   self.assertEqual([e.kind for e in s.handle(event)],[0xae])
   enemy=next(n for n in s.dungeon_run.current['npcs'] if n['template']==1367)
   self.assertEqual(s.handle(death(enemy)),[])
   self.assertEqual(s.handle(Event(0x202,kind=0x225,payload=struct.pack('>iB',s.account.get_location()['map'],0)))[-1].kind,0x226)
   retry,t2=start(38300,path);self.assertFalse(retry.dungeon_failed)
   self.assertNotEqual(retry.reward_run_id,s.reward_run_id);finish(retry,t2)
   self.assertEqual(retry.account.get_reward_balances()['ed'],120)

 def test_source_controller_can_report_unattributed_self_destruction(self):
  s,t=start(33302)
  helper=next(n for n in s.dungeon_run.current['npcs'] if n['template']==1898)
  def unattributed(n):
   e=death(n);raw=bytearray(e.payload);struct.pack_into('>QQ',raw,5,0,0);struct.pack_into('>Q',raw,len(raw)-8,0)
   return Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
  self.assertEqual(s.handle(unattributed(s.dungeon_run.current['npcs'][0])),[])
  self.assertEqual(s.handle(unattributed(helper))[0].kind,0xae)

 def test_finite_source_rooms_and_local_henir_rotations(self):
  for identity,count in [(41400,4),(35880,6),(38100,20)]:
   s,t=start(identity);rooms=finish(s,t)
   self.assertEqual(rooms,count)
  s,t=start(35080);finish(s,t)
  self.assertTrue({1,2,3}<=s.dungeon_run.completed_stages)

if __name__=='__main__':unittest.main()
