"""Source-route admission, complete solo replay and durable per-map clears."""
import json,struct,sys,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from els_server.domain.dungeon_routes import route_catalog,DungeonRun
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
BODY=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]['payload'])
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def death(npc,uid=1001):
 b=bytearray(BODY);struct.pack_into('>i',b,0,npc['key']);struct.pack_into('>f',b,46,npc['hp'])
 return Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
def start(identity,path=None):
 s=LocalSession(LocalAccount(LocalState(path)) if path else None,True,True,'dx11_260923',
    npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=path is not None,item_test=path is not None)
 s.role='game';s.phase='town_ready'
 from els_server.game_data import client_data
 single=1 in client_data().dungeon(identity).get('DUNGEON_CHECK_CONDITION',{}).values()
 assert s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',2 if single else 1,identity)))[0].payload[:4]==bytes(4)
 assert [e.kind for e in s.handle(Event(0x202,kind=0x37f if single else 0x382,payload=ENTRY))]==[0x380 if single else 0x383,0x14a]+([0xae6] if str(identity) in route_catalog()._data['internal_routes'] else [])
 assert [e.kind for e in s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))]==[0x92,0x93,0x96,0xb2]
 t=[0.0];s.dungeon_run.clock=lambda:t[0]
 load(s)
 return s,t

def load(s):
 reply=s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))
 assert [e.kind for e in reply][:5]==[0xb4,0xb5,0xb6,0xb7,0xbd]
 assert reply[3].payload==struct.pack('>b',s.dungeon_run.part)

def finish(s,t):
 seen=set();rooms=0
 while not s.clear_notified:
  run=s.dungeon_run;cursor=(run.stage,run.part,frozenset(run.completed_stages))
  assert cursor not in seen,('route loops',run.identity,cursor)
  seen.add(cursor);rooms+=1
  if not s.part_end_notified:assert s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',run.part)))==[]
  # All declared source objects are legitimate; extras must never satisfy
  # missing source keycode/type conditions or confer a duplicate grant.
  for npc in run.current['npcs']:
   if npc.get('team',1)==0 or run.identity==38300 and npc['template']==1368:continue
   event=death(npc);reply=s.handle(event)
   assert reply and reply[0].kind==0xae,(run.identity,cursor,npc['key'])
   assert [e.kind for e in s.handle(event)]==[0xae]
  if any(c['kind']==5 for c in run.current['conditions']):
   self_reply=s.handle(Event(0x202,kind=0xb8,payload=struct.pack('>b',run.part)))
   assert self_reply[0].kind==0xb9 and self_reply[0].payload==bytes(4)
  t[0]+=86401;s.periodic_notifications()
  t[0]+=86401;s.periodic_notifications()
  assert s.part_end_notified,(run.identity,cursor,'no end')
  part=run.part;reply=s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',part)))
  assert reply[0].kind==0xbc
  if any(e.kind==0xb2 for e in reply):load(s)
  if s.clear_notified:
   assert any(e.kind==0xc1 for e in reply)
   assert [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',part)))]==[0xbc]
 return rooms

class DungeonRoutesTests(unittest.TestCase):
 def test_all_admitted_routes_reach_real_clear(self):
  result={};cat=route_catalog()
  for identity in map(int,cat._data['routes']):
   if identity==30000:continue
   with self.subTest(dungeon=identity):
    s,t=start(identity);result[identity]=finish(s,t)
  (ROOT/'analysis/dungeon-chain-20261015/replayed-routes.json').write_text(json.dumps(result,indent=2))
 def test_persistent_reward_map_retry_return_and_reentry(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s,t=start(30092,path);before=s.account.get_reward_balances()['ed']
   finish(s,t);saved=s.account.get_inventory_snapshot()
   self.assertEqual(saved['balances']['ed']-before,120)
   self.assertEqual(LocalAccount(LocalState(path)).get_inventory_snapshot(),saved)
   self.assertEqual(s.handle(Event(0x202,kind=0x225,payload=struct.pack('>iB',s.account.get_location()['map'],0)))[-1].kind,0x226)
   s.phase='town_ready';old_run=s.reward_run_id
   s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30102)))
   s.handle(Event(0x202,kind=0x382,payload=ENTRY))
   self.assertNotEqual(s.reward_run_id,old_run)
   self.assertEqual(s.dungeon_run.identity,30102)
   self.assertEqual(s.world_drops,{})
   s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
   t2=[0.0];s.dungeon_run.clock=lambda:t2[0];load(s);finish(s,t2)
   self.assertEqual(s.account.get_reward_balances()['ed'],before+240)
 def test_fake_early_clear_and_future_npc(self):
  s,t=start(30092)
  self.assertFalse(s.part_end_notified)
  npc={**s.dungeon_run.current['npcs'][0],'key':99999}
  self.assertEqual(s.handle(death(npc)),[])
  self.assertEqual(s.handle(Event(0x202,kind=0xbb,payload=b'\0')),[])
  s.phase='town_ready'
  self.assertNotEqual(s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,123456)))[0].payload[:4],bytes(4))
 def test_scope_and_every_stage_serialization(self):
  cat=route_catalog();scope=json.loads((ROOT/'config/dungeon_scope.json').read_text(encoding='utf8'))
  self.assertEqual(set(cat._data['routes'])|set(cat.manifest['unsupported']),set(scope['active']))
  self.assertFalse(set(cat._data['routes']) & (set(scope['excluded'])|set(scope['pending'])))
  for identity,route in cat._data['routes'].items():
   run=DungeonRun(int(identity),str(uuid.uuid4()))
   for stage in run.graph['stages']:
    run._load_stage(int(stage))
    self.assertEqual(struct.unpack_from('>i',run.population_event().payload)[0],int(stage))
    keys=[n['key'] for p in run.parts.values() for n in p['npcs']]
    self.assertEqual(len(keys),len(set(keys)))
  s=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True)
  s.role='game';s.phase='town_ready'
  for identity in scope['excluded']:
   result=s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,int(identity))))[0].payload[:4]
   self.assertEqual(result,bytes(4) if int(identity) in cat.entry_aliases else struct.pack('>i',817))
 def test_portal_requires_native_request_after_kills(self):
  from els_server.domain.dungeon_routes import DungeonRun
  run=DungeonRun(32982,str(uuid.uuid4()));found=False
  for stage in run.graph['stages']:
   run._load_stage(int(stage))
   for part,room in run.parts.items():
    if not any(c['kind']==5 for c in room['conditions']):continue
    run.part=part;run.loaded();run.defeated={n['key']:b'proof' for n in room['npcs']}
    self.assertFalse(run.poll_ready())
    run.portal_requested=True
    self.assertTrue(any(run.condition_ready(c) for c in room['conditions']))
    found=True;break
   if found:break
  self.assertTrue(found)
 def test_b2_preserves_original_el_tree_bytes(self):
  # The generic serializer must match the independently native-verified B2
  # framing and the 8/11/2 source population, including empty trailing maps.
  from els_server.domain.dungeon_population import substage,population
  run=DungeonRun(30000,str(uuid.uuid4()))
  for stage in range(3):
   run._load_stage(stage)
   self.assertEqual([n['template'] for n in run.parts[0]['npcs']],[n['template'] for n in population(stage)['npcs']])
   self.assertEqual(run.population_event().payload,substage(stage,boss_gauge=True).payload)

 def test_queued_portal_after_completed_part_is_read_only(self):
  s,t=start(30242);run=s.dungeon_run
  def portal(part):return Event(0x202,kind=0xb8,payload=struct.pack('>b',part))
  self.assertEqual(s.handle(portal(run.part))[0].payload,struct.pack('>i',-1))
  old=run.part
  for npc in run.current['npcs']:
   if npc.get('team',1)!=0:s.handle(death(npc))
  t[0]+=86401;s.periodic_notifications()
  reply=s.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',old)))
  self.assertEqual([e.kind for e in reply],[0xbc,0xb7,0xbd])
  self.assertNotEqual(run.part,old)
  before=(run.stage,run.part,dict(run.defeated),run.next,s.part_end_notified,run.portal_requested)
  for part in (old,run.part,old,run.part):
   reply=s.handle(portal(part));self.assertEqual([(e.kind,e.payload) for e in reply],[(0xb9,bytes(4))])
   self.assertEqual((run.stage,run.part,dict(run.defeated),run.next,s.part_end_notified,run.portal_requested),before)
  self.assertEqual(s.handle(portal(99))[0].payload,struct.pack('>i',-1))
  self.assertEqual(s.handle(Event(0x202,kind=0xb8,payload=b''))[0].payload,struct.pack('>i',-1))
  # Once this room really clears, its own portal request still satisfies a
  # source portal condition instead of being swallowed as a duplicate.
  for npc in run.current['npcs']:
   if npc.get('team',1)!=0:s.handle(death(npc))
  self.assertEqual(s.handle(portal(run.part))[0].payload,bytes(4));self.assertTrue(run.portal_requested)
  finish(s,t)
  self.assertEqual([(e.kind,e.payload) for e in s.handle(portal(run.part))],[(0xb9,bytes(4))])

 def test_current_manual_family_icons_use_admitted_route_and_solo_continuation(self):
  cat=route_catalog();self.assertEqual(cat.entry_identity(30240),30242)
  self.assertEqual(cat.entry_identity(30241),30242);self.assertEqual(cat.entry_identity(33030),33030)
  for mode in (1,2):
   s,t=start(30242);s.phase='town_ready'
   reply=s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',mode,30240)))
   self.assertEqual(reply[0].payload,struct.pack('>ii',0,1));self.assertEqual(s.requested_dungeon_id,30242)
   self.assertEqual([e.kind for e in s.handle(Event(0x202,kind=0x382,payload=ENTRY))],[0x383,0x14a])
   self.assertEqual(s.dungeon_run.identity,30242)
   self.assertFalse(cat.supports(30240))
  self.assertEqual(s.dungeon_run.graph['source'],cat.graph(30242)['source'])

if __name__=='__main__':unittest.main()
