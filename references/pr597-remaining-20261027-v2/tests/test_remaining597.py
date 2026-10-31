"""Counterexamples for the remaining597 server repairs; real temporary SQL."""
import copy,json,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession,SessionOrderError
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import skill_unlocks as books
from els_server.storage.seal_quests import QuestState,ensure
from els_server.domain.seal_quests import quest_catalog
from els_server.protocol.protocol_codec import Event,encode_event,decode_event
from els_server.protocol import quest_messages
from els_server.domain import dungeon_flow,dungeon_routes,devildom1_raid2_controllers as raid

OWNER=1001;MAX=2**64-1
def death(index,hp,flag=255,owner=OWNER):
 return Event(0x202,performers=(0,),kind=0xad,payload=(
  struct.pack('>iBQQ6fBI',index,flag,MAX if flag==255 else owner,MAX if flag==255 else owner,*([0.]*6),1,struct.unpack('>I',struct.pack('>f',float(hp)))[0])
  +struct.pack('>I',0)+struct.pack('>IQB',1,owner,0)+struct.pack('>Q',0)+struct.pack('>I',0)+struct.pack('>Q',0 if flag==255 else owner)))

class SqlFixture(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'own.db'
  self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=?',(OWNER,));ensure(db)
   q=35360;counts={str(s['m_iID']):0 for s in quest_catalog().objectives(q)}
   db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(OWNER,q,123,1,json.dumps(counts)))
 def dump(self):
  with closing(sqlite3.connect(self.path))as db,db:return tuple(db.iterdump())
 def book(self):
  row=next(r for r in __import__('els_server.domain.skill_unlocks',fromlist=['catalog']).catalog()['books'].values()if r['seal_group']==5)
  with closing(sqlite3.connect(self.path))as db,db:item=grant_items(db,[dict(template=row['template'],metadata=0,group=4,quantity=1)],OWNER)[0]
  return struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
 def test_fresh_book_projection_replay_and_cold_read_preserve_progress(self):
  self.assertIn(35360,[q['id']for q in QuestState(self.path).notification_snapshot()['active']])
  p=self.book();first=books.use_skill_book(self.path,OWNER,p,'own-first')
  self.assertFalse(first['replayed']);self.assertEqual(first['quest_notification'].kind,0x2b)
  self.assertEqual(struct.unpack_from('>I',first['quest_notification'].payload,4)[0],0)
  self.assertNotIn(35360,[q['id']for q in QuestState(self.path).notification_snapshot()['active']])
  with closing(sqlite3.connect(self.path))as db,db:
   self.assertEqual(db.execute('SELECT accepted_at,generation FROM character_quests WHERE owner=? AND quest=35360',(OWNER,)).fetchone(),(123,1))
   self.assertEqual(db.execute('SELECT COUNT(*) FROM completed_quests WHERE owner=? AND quest=35360',(OWNER,)).fetchone(),(0,))
  snap=self.dump();again=books.use_skill_book(self.path,OWNER,p,'own-first')
  self.assertTrue(again['replayed']);self.assertEqual(again['quest_notification'],first['quest_notification']);self.assertEqual(self.dump(),snap)
  other=self.a.characters.create('OtherOwn',2,'other')
  self.assertNotIn(5,other.get('skill_seal_groups',()))
 def test_quest_and_frame_encoding_failure_rollback_book_seal_and_receipt(self):
  p=self.book();snap=self.dump()
  for target in ('els_server.protocol.quest_messages.initialization','els_server.protocol.protocol_codec.encode_event'):
   with self.subTest(target=target),patch(target,side_effect=ValueError('own-encoding-failure')):
    with self.assertRaises(ValueError):books.use_skill_book(self.path,OWNER,p,'encode-fail')
   self.assertEqual(self.dump(),snap)
  self.assertFalse(books.use_skill_book(self.path,OWNER,p,'encode-fail')['replayed'])
 def test_session_returns_prepared_quest_refresh_and_retry_no_second_unlock(self):
  p=self.book();s=LocalSession(self.a,enter_town=True,client_build='dx11_260923');s.item_test=True;s.role='game';s.phase='town_ready'
  ev=Event(0x202,kind=0x219,payload=p)
  self.assertEqual([e.kind for e in s.handle(ev,request_sequence=1)],[0x21a,0x131,0x55b,0x2b])
  snap=self.dump();self.assertEqual([e.kind for e in s.handle(ev,request_sequence=1)],[0x21a,0x55b,0x2b]);self.assertEqual(self.dump(),snap)
 def test_ed_service_refresh_failure_rolls_back_price_and_unlock(self):
  from els_server.storage.shop_state import purchase
  from els_server.domain.skill_book_shop import offers
  offer=offers()[4];payload=struct.pack('>IIH',1,offer['sku'],1)
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=1000 WHERE uid=?',(OWNER,))
  notifications=[]
  def prepare(db,character,previous,replayed):notifications.extend(books.purchase_notifications(db,OWNER,character,previous,replayed))
  snap=self.dump()
  with patch('els_server.protocol.quest_messages.initialization',side_effect=ValueError('own-shop-encode')):
   with self.assertRaises(ValueError):purchase(self.path,payload,'own-service',OWNER,prepare_skill_books=prepare)
  self.assertEqual(self.dump(),snap)
  purchase(self.path,payload,'own-service',OWNER,prepare_skill_books=prepare)
  self.assertEqual([e.kind for e in notifications],[0x131,0x55b,0x2b]);notifications.clear()
  snap=self.dump();purchase(self.path,payload,'own-service',OWNER,prepare_skill_books=prepare)
  self.assertEqual(self.dump(),snap);self.assertEqual([e.kind for e in notifications],[0x131,0x55b,0x2b])
 def test_known_town_default_position_refusal_leaves_state_and_sql(self):
  s=LocalSession(self.a,enter_town=True,client_build='dx11_260923');s.role='game';s.phase='map_loading'
  ev=Event(0x202,performers=(0,),kind=0x225,payload=struct.pack('>iB',20000,1))
  snap=self.dump();before=(s.phase,s.pending_map,s.account.get_location())
  reply=s.handle(ev,request_sequence=7)
  self.assertEqual([(e.kind,e.payload)for e in reply],[(0x226,struct.pack('>iiiii',-1,20000,0,0,0))])
  self.assertEqual((s.phase,s.pending_map,s.account.get_location()),before);self.assertEqual(self.dump(),snap)
  for bad in (struct.pack('>iB',999999,1),struct.pack('>iB',20000,2),b''):
   with self.assertRaises(SessionOrderError):s.handle(Event(0x202,performers=(0,),kind=0x225,payload=bad),request_sequence=8)

class Clock:
 def __init__(self):self.value=0.;self.total=0.;self.started=None
 def __call__(self):return self.value
 def pause(self):self.started=None
 def resume(self):self.started=self.value
def fixture(stage=0):
 c=Clock();run=dungeon_routes.DungeonRun(34140,'00000000-0000-0000-0000-000000000341',clock=c)
 if stage:run.stage=stage;run._load_stage(stage)
 run.loaded()
 s=NS(dungeon_run=run,account=NS(uid=OWNER),role='game',phase='dungeon_active',dungeon_substage_synced=True,
  clear_notified=False,dungeon_failed=False,part_end_notified=False,dungeon_clock=c,
  dungeon_participants=frozenset((OWNER,)),reward_run_id=run.run_id,reward_transaction=None,
  summon_keys=set(),defeated_npcs=run.defeated,challenge_deadline=None,application=None,
  drop_probe=False,world_drops={},world_drop_sequence=0,gate_stage_loading=False,gate_stage=stage,
  previous_dungeon_part=None,summon_deaths={},summon_requests={},summon_next_key=16)
 return s,run,c
class RaidBoundaryTests(unittest.TestCase):
 def test_two_dragon_doors_require_all_hostiles_and_original_graph(self):
  for stage in (0,1):
   r=dungeon_routes.DungeonRun(30182,'00000000-0000-0000-0000-000000000182')
   r.stage=stage;r._load_stage(stage);r.part=1
   cond=next(c for c in r.current['conditions']if c['kind']==3 and c['required']==[145])
   self.assertFalse(r.condition_ready(cond))
   live=[n for n in r.current['npcs']if n['active']and n.get('team',1)!=0]
   for n in live[:-1]:r.defeated[n['key']]=b'proof'
   self.assertFalse(r.condition_ready(cond));r.defeated[live[-1]['key']]=b'proof'
   self.assertTrue(r.condition_ready(cond))
   r.graph['source_sha256']='0'*64;self.assertFalse(r.condition_ready(cond))
  s,r,c=fixture()
  for n in r.current['npcs']:
   if n['active']:r.defeated[n['key']]=b'proof'
  self.assertFalse(r.condition_ready(r.current['conditions'][0]))
 def test_three_finale_rooms_do_not_clear_or_invent_part_before_boss(self):
  for identity,stage in ((35320,3),(35321,2),(35322,0)):
   s,_,clock=fixture();r=dungeon_routes.DungeonRun(identity,'00000000-0000-0000-0000-000000000322',clock=clock)
   r.stage=stage;r._load_stage(stage);r.loaded();s.dungeon_run=r;s.reward_run_id=r.run_id
   self.assertNotIn('1',r.graph['stages'][str(stage)]['parts'])
   for n in r.current['npcs']:
    if n['template']!=9431:r.defeated[n['key']]=b'accepted-source-retirement'
   self.assertTrue(dungeon_flow.finale_boss_pending(r));self.assertEqual(dungeon_flow.periodic(s),[])
   self.assertEqual(r.part,0);self.assertIsNone(r.next)
   s.part_end_notified=True
   with patch('els_server.domain.raid_economy_flow.solo',side_effect=AssertionError('premature dispatch')):
    self.assertEqual(dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xbb,payload=b'\0')),[])
   s.part_end_notified=False
   for n in r.current['npcs']:
    if n['template']==9431:r.defeated[n['key']]=b'accepted-boss-death'
   self.assertFalse(dungeon_flow.finale_boss_pending(r));events=dungeon_flow.periodic(s);clock.value+=20
   self.assertEqual([e.kind for e in events+dungeon_flow.periodic(s)],[0xba])
 def test_nine_exact_native_markers_preserve_hostile_gate(self):
  seen=[]
  for stage in (0,1,2):
   s,r,c=fixture(stage)
   for npc in r.current['npcs']:
    if (stage,npc['key'])not in raid.CONTROLLERS:continue
    self.assertIsNotNone(raid.source_rule(r,npc));seen.append((stage,npc['key']))
    ev=death(npc['key'],npc['hp'])
    with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease',return_value=True):
     got=dungeon_flow.handle(s,ev)
    self.assertEqual([e.kind for e in got],[0xae,0xaf])
   c.value=20
   self.assertEqual(dungeon_flow.periodic(s),[]);self.assertFalse(s.part_end_notified)
   # Even a forged old end notification cannot reach the original raid writer.
   s.part_end_notified=True
   with patch('els_server.domain.raid_economy_flow.solo',side_effect=AssertionError('settled live boss')):
    self.assertEqual(dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xbb,payload=b'\0')),[])
   s.part_end_notified=False
   for n in r.current['npcs']:
    if n['active']and n.get('team',1)!=0:r.defeated[n['key']]=b'accepted-combat-proof'
   self.assertFalse(raid.gate_blocked(r));dungeon_flow.periodic(s);c.value+=6
   self.assertEqual([e.kind for e in dungeon_flow.periodic(s)],[0xba])
  self.assertEqual(len(seen),9)
 def test_expiry_identity_owner_bytes_and_encoding_fail_closed(self):
  s,r,c=fixture();n=next(n for n in r.current['npcs']if n['key']==7);ev=death(7,n['hp'])
  from els_server.domain.dungeon_lifecycle import death_report
  with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease',return_value=True):
   for bad in (death(7,n['hp'],owner=OWNER+1),death(7,n['hp']+1),Event(0x202,kind=0xad,payload=ev.payload),death(0,n['hp'])):
    self.assertIn(raid.handle(s,bad,death_report(bad.payload)),(None,[]));self.assertFalse(r.defeated)
   with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('own-fail')):
    with self.assertRaises(ValueError):raid.handle(s,ev,death_report(ev.payload))
   self.assertFalse(r.defeated);self.assertIsNone(r.next)
   self.assertEqual([e.kind for e in raid.handle(s,ev,death_report(ev.payload))],[0xae,0xaf])
   self.assertEqual([e.kind for e in raid.handle(s,ev,death_report(ev.payload))],[0xae])
   bad=death(7,n['hp']);raw=bytearray(bad.payload);struct.pack_into('>f',raw,21,1.)
   bad=Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
   self.assertEqual(raid.handle(s,bad,death_report(bad.payload)),[])
 def test_late_death_after_clear_or_failure_never_reads_expired_population(self):
  class ExpiredRun:
   identity=34140;stage=2;part=0;visits=0;graph={'source_sha256':raid.GRAPH_SHA}
   catalog=NS(graph=lambda identity: {'source_sha256':raid.GRAPH_SHA})
   @property
   def current(self):raise AssertionError('expired population read')
  for failed in (False,True):
   s,r,c=fixture();s.dungeon_run=ExpiredRun();s.clear_notified=not failed;s.dungeon_failed=failed;s.part_end_notified=True
   with patch('els_server.domain.raid_economy_flow.solo',return_value=None):
    self.assertEqual([e.kind for e in dungeon_flow.handle(s,death(999,1))],[0xae])
    self.assertEqual(dungeon_flow.handle(s,Event(0x202,kind=0xad,payload=death(999,1).payload)),[])
    self.assertEqual(dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xad,payload=b'bad')),[])
    if s.clear_notified:self.assertEqual([e.kind for e in dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xbb,payload=b'\0'))],[0xbc])

if __name__=='__main__':unittest.main()
