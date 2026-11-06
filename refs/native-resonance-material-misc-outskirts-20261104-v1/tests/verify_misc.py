import runtime_inputs
import collections,copy,hashlib,importlib.util,io,json,sqlite3,struct,sys,time,unittest,uuid
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
W=Path(__file__).resolve().parent;R=Path('G:/els')
spec=importlib.util.spec_from_file_location('misc_owned_fixture',R/'analysis/pr771-firstbatch-20261103-v1/test_secondbatch.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
from els_server.domain import ordinary_misc_loot as rules
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.friends_spawns import capture_static_origin
from els_server.domain.drop_pickup import native_modes,ground_pickup_request
from els_server.domain.region_quests import region_catalog
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_state import load_items,grant_items,InventoryFull
source=json.loads((R/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_bytes())
BODY=bytes.fromhex(next(e['payload_hex']for e in source['server']if e.get('event')=='decoded_client_event'and e.get('kind')==0xd0))[:320]
def pickup(drop):
 raw=b''
 for field in native_modes()[4]['fields']:
  name=field['field'];mask=field.get('xor',0)
  if name=='item':raw+=struct.pack('>I',drop['template'])+BODY[4:]
  elif name=='opaque':raw+=struct.pack('>I',3)+b'own'
  elif name=='drop_id':raw+=struct.pack('>I',drop['drop_id']^mask)
  elif name=='flag':raw+=bytes([mask])
  else:raw+=struct.pack('>3f',*drop['xyz'])
 ground_pickup_request(raw)
 return Event(0x202,performers=(0,),kind=0xd0,payload=raw)
DETAILS=[]
class Misc(unittest.TestCase):
 setUp=fixture.SecondBatch.setUp
 party=fixture.SecondBatch.party
 def arrange(self,mid,boss=False,party=False):
  if party:
   app,room,members=self.party();room.identity=mid;room.party['members']=list(members);room.party['id']=873
   app.world.parties[873]=room.party;epoch=room.seed
  else:
   app=self.app;room=None;s=fixture.SecondBatch.dungeon(self,mid);members=(s,);epoch=s.reward_run_id
  with closing(sqlite3.connect(self.path))as db,db:
   for s in members:
    for qid in region_catalog().data['quests']:db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(s.account.uid,int(qid),1000,'{}'))
  leader=members[0];run=DungeonRun(mid,epoch,clock=lambda:self.t[0]);selected=None
  for sk in run.graph['stages']:
   run._load_stage(int(sk))
   for pk,part in run.parts.items():
    candidate=next((n for n in part['npcs']if bool(n['boss'])==boss and n['active']and not n['no_drop']and not n.get('ally')and n.get('team',1)!=0),None)
    if candidate is not None:selected=(int(sk),pk,candidate['key']);break
   if selected is not None:break
  self.assertIsNotNone(selected,mid)
  for s in members:
   run=DungeonRun(mid,epoch,clock=lambda:self.t[0]);run._load_stage(selected[0]);run.part=selected[1];run.loaded()
   s.dungeon_run=run;s.dungeon_id=mid;s.gate_stage=run.stage;s.phase='dungeon_active';s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.dungeon_failed=False;s.defeated_npcs=run.defeated
  if room is not None:capture_static_origin(room)
  npc=next(n for n in leader.dungeon_run.current['npcs']if n['key']==selected[2])
  return app,room,members,npc
 def hit(self,leader,npc):
  original=rules.plans
  with patch('els_server.domain.ordinary_misc_loot.plans',side_effect=lambda s,r,bp:original(s,lambda n:0,bp)):
   return leader.handle(fixture.death(npc,leader.account.uid),900)
 def pickup_all(self,s):
  drops=[d for d in s.world_drops.values()if d.get('source')==rules.POLICY]
  self.assertTrue(drops)
  for index,drop in enumerate(drops):
   before=s.account.get_inventory_snapshot();event=pickup(drop);reply=s.handle(event,1000+index)
   self.assertIn(0xd1,[e.kind for e in reply],(drop,[hex(e.kind)for e in reply]))
   self.assertEqual(struct.unpack('>i',next(e.payload for e in reply if e.kind==0xd1))[0],0)
   saved=s.account.get_inventory_snapshot();self.assertNotEqual(saved,before)
   again=s.handle(event,1100+index);self.assertIn(0xd1,[e.kind for e in again]);self.assertEqual(saved,s.account.get_inventory_snapshot())
   with closing(sqlite3.connect(self.path))as db:self.assertEqual(sum(i['count']for i in load_items(db,s.account.uid)if i['template']==drop['template']),sum(i['count']for i in saved['items']if i['template']==drop['template']))
  return drops
 def case(self,mid,boss=False,party=False):
  app,room,members,npc=self.arrange(mid,boss,party);leader=members[0];reply=self.hit(leader,npc)
  self.assertIn(0xcf,[e.kind for e in reply],(mid,boss,party,[hex(e.kind)for e in reply]))
  issued=[]
  for s in members:
   drops=self.pickup_all(s);templates={d['template']for d in drops};self.assertTrue({109945,109955,130047,163135,701000}<=templates)
   if str(mid)in rules.catalog()['maps']and rules.catalog()['maps'][str(mid)]['ingredients']:self.assertIn(99809,templates)
   regional=rules.catalog()['maps'][str(mid)]['regional_ingredients']
   if regional:self.assertIn(regional[0],templates)
   gear=rules.catalog()['maps'][str(mid)]['equipment']
   if boss and gear:self.assertTrue(templates&set(gear))
   issued.append(sorted(templates))
  before=[s.account.get_inventory_snapshot()for s in members];count=[len(s.world_drops)for s in members]
  leader.handle(fixture.death(npc,leader.account.uid),1200)
  self.assertEqual(before,[s.account.get_inventory_snapshot()for s in members]);self.assertEqual(count,[len(s.world_drops)for s in members])
  DETAILS.append(dict(map=mid,boss=boss,members=len(members),templates=issued,native_D0=True,cold_read=True))
 def test_solo_legacy_source(self):self.case(30092)
 def test_solo_modern_fallback(self):self.case(34330)
 def test_solo_material_boss(self):self.case(34330,boss=True)
 def test_party_ordinary(self):self.case(30092,party=True)
 def test_party_modern(self):self.case(34760,party=True)
 def test_party_material_boss(self):self.case(34330,boss=True,party=True)
 def test_solo_accessory(self):self.case(30102,boss=True)
 def test_party_accessory(self):self.case(30102,boss=True,party=True)
 def test_elrianode_regional_ingredient(self):self.case(34000)
 def test_varnimyr_regional_ingredient(self):self.case(34110,party=True)
 def test_hamel_ingredient_pool_is_not_global(self):
  self.assertTrue({99821,99822}<=set(rules.catalog()['maps']['33122']['ingredients']))
  self.assertFalse({99821,99822}&set(rules.catalog()['maps']['30092']['ingredients']))
  self.assertEqual(rules.catalog()['maps']['34000']['regional_ingredients'],[700245,700246])
  self.assertEqual(rules.catalog()['maps']['34110']['regional_ingredients'],[700247,700248])
 def test_late_party_encoding_failure_rolls_back_all_drops_and_exp(self):
  app,room,members,npc=self.arrange(34760,party=True);leader=members[0]
  before=[s.account.get_inventory_snapshot()for s in members]
  from els_server.domain import pve_economy_flow
  with patch('els_server.domain.party_commands._prepared_boxes',side_effect=ValueError('owned-misc-late-encode')):
   with self.assertRaisesRegex(ValueError,'owned-misc-late-encode'):pve_economy_flow.death(members,fixture.death(npc,leader.account.uid),leader,room)
  self.assertTrue(all(not s.dungeon_run.defeated for s in members));self.assertTrue(all(not s.world_drops for s in members));self.assertEqual(before,[s.account.get_inventory_snapshot()for s in members])
  with closing(sqlite3.connect(self.path))as db:
   self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='ordinary_misc_loot_issues'").fetchone())
 def test_pickup_encoding_failure_rolls_back_item_and_source(self):
  app,room,members,npc=self.arrange(34330);s=members[0];self.hit(s,npc)
  drop=next(d for d in s.world_drops.values()if d.get('source')==rules.POLICY and d['template']==130047);before=s.account.get_inventory_snapshot()
  with patch('els_server.domain.dungeon_drops.pickup_inventory_notice',side_effect=ValueError('owned-pickup-encode')):self.assertEqual(s.handle(pickup(drop),1500),[])
  self.assertEqual(before,s.account.get_inventory_snapshot());self.assertFalse(drop['pickup_committed'])
  self.assertTrue(s.handle(pickup(drop),1501));self.assertNotEqual(before,s.account.get_inventory_snapshot())
 def test_inventory_full_keeps_issue_unclaimed(self):
  app,room,members,npc=self.arrange(34330);s=members[0];self.hit(s,npc);drop=next(d for d in s.world_drops.values()if d.get('source')==rules.POLICY)
  before=s.account.get_inventory_snapshot()
  with patch('els_server.storage.ordinary_misc_loot.grant_items',side_effect=InventoryFull('owned-full')):
   reply=s.handle(pickup(drop),1600);self.assertEqual(struct.unpack('>i',reply[0].payload)[0],-1)
  self.assertEqual(before,s.account.get_inventory_snapshot());self.assertFalse(drop['pickup_committed']);self.assertTrue(s.handle(pickup(drop),1601))
 def test_wrong_template_and_unissued_id_never_grant(self):
  app,room,members,npc=self.arrange(34330);s=members[0];self.hit(s,npc);drop=next(d for d in s.world_drops.values()if d.get('source')==rules.POLICY);before=s.account.get_inventory_snapshot()
  for bad in(dict(drop,template=710003),dict(drop,drop_id=drop['drop_id']+999999)):
   self.assertEqual(s.handle(pickup(bad),1700),[])
  self.assertEqual(before,s.account.get_inventory_snapshot())
 def test_noncombat_and_dynamic_actors_have_no_misc_source(self):
  app,room,members,npc=self.arrange(34330);s=members[0]
  for field,value in(('active',False),('no_drop',True),('ally',True),('team',0),('dynamic',True)):
   self.assertIsNone(rules.source(s,dict(npc,**{field:value})))
 def test_all_281_factories_encode_and_rollback(self):
  from els_server.domain.raid_reward_items import _issue_source,ensure_sources
  from els_server.domain.reward_rules import item_plan
  from els_server.domain.dungeon_drops import pickup_inventory_notice
  counts=collections.Counter()
  with closing(sqlite3.connect(self.path))as db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');ensure_sources(db)
   for key,row in rules.catalog()['items'].items():
    template=int(key)
    if template==135911:continue # its real exact giant-Boss issue is tested separately
    db.execute('SAVEPOINT one_factory');plan=[item_plan(template,1)]
    cap=_issue_source(db,self.a.uid,'factory-only:'+key,'ordinary',dict(owned_factory_fixture=True),plan,lambda d:True)
    result=grant_items(db,plan,self.a.uid,raid_reward_source=cap);self.assertEqual(result[0]['template'],template);encode_event(pickup_inventory_notice(result));counts[row['item_type']]+=1
    db.execute('ROLLBACK TO one_factory');db.execute('RELEASE one_factory')
   db.rollback()
  DETAILS.append(dict(factory_contracts=sum(counts.values()),by_item_type=dict(counts),controlled_factory_only=True))
 def test_current_map_equipment_pool_all_roles(self):
  from types import SimpleNamespace as NS
  reached=set();p=rules.catalog()
  for mid,row in p['maps'].items():
   for family in range(1,16):
    pool=[t for t in row['equipment']if row['wear_family'][str(t)]in(0,family)]
    if not pool:continue
    for index,target in enumerate(pool):
     seq=iter([9999]*(5+len(row['extra_materials'])+bool(row['ingredients'])+bool(row['regional_ingredients']))+[0,index])
     result=rules.plans(NS(c={'dungeon':int(mid),'stage':row.get('equipment_stage',0)},origin={'boss':True},family=family),lambda n:next(seq),0)
     self.assertEqual([(t,n)for t,n in result if p['items'][str(t)]['item_type']in(1,2,3)],[(target,1)]);reached.add(target)
  expected={int(t)for t,r in p['items'].items()if r['item_type']in(1,2,3)};self.assertEqual(reached,expected)
  DETAILS.append(dict(equipment_role_selection_templates=len(reached),maps=len(p['maps']),role_families=15))
 def test_source_epoch_change_rejects_before_commit(self):
  app,room,members,npc=self.arrange(34330);s=members[0];source=rules.source(s,npc)
  before=s.dungeon_run.run_id;s.dungeon_run.run_id=str(uuid.uuid4())
  try:
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE')
    with self.assertRaisesRegex(ValueError,'source changed'):source.validate(db)
  finally:s.dungeon_run.run_id=before
 def test_first_el_tree_uses_existing_death_writer(self):
  from els_server.domain.pve_economy_flow import bind_story
  from els_server.domain.dungeon_population import population
  s=fixture.SecondBatch.dungeon(self,30092);s.dungeon_run=None;s.dungeon_id=30000;s.reward_run_id=str(uuid.uuid4());s.gate_stage=0;s.defeated_npcs={}
  bind_story(s);npc=next(n for n in population(0)['npcs']if n['active']and not n['no_drop']and not n.get('ally')and n.get('team',1)!=0)
  reply=self.hit(s,npc);self.assertIn(0xcf,[e.kind for e in reply]);self.pickup_all(s)
 def test_party_misc_pickup_after_real_clear(self):
  prior=R/'analysis/new-role-materials-outskirts-20261104-v1/verify_feedback.py'
  spec=importlib.util.spec_from_file_location('prior_misc_clear_fixture',prior);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  app,room,members,npc=module.Feedback.arrange(self,34330);leader=members[0];self.hit(leader,npc)
  for s in members:s.gate_stage=s.dungeon_run.stage
  self.t[0]+=100000;app.world.dungeons.periodic(leader);self.assertEqual(room.phase,'part_end')
  for index,s in enumerate(members):s.handle(fixture.bb(s),2100+index)
  self.assertEqual(room.phase,'clear');self.assertTrue(all(s.clear_notified for s in members))
  for s in members:self.pickup_all(s)
 def test_original_bait_pickup_remains_connected(self):
  prior=R/'analysis/new-role-materials-outskirts-20261104-v1/verify_feedback.py'
  spec=importlib.util.spec_from_file_location('prior_material_fixture',prior);prior_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior_module)
  app,room,members,npc=prior_module.Feedback.arrange(self,34320);leader=members[0]
  for s in members:s.gate_stage=s.dungeon_run.stage
  from els_server.domain.friends_material_loot import accepted_death as original
  with patch('els_server.domain.friends_material_loot.accepted_death',side_effect=lambda d,r,s,e:original(d,r,s,e,randbelow=lambda n:0)):
   result=leader.handle(fixture.death(npc,leader.account.uid),2300)
  self.assertIn(0xcf,[e.kind for e in result])
  from els_server.domain.fishing_bait_loot import POLICY as BAIT
  for s in members:
   drop=next((d for d in s.world_drops.values()if d.get('source')==BAIT),None);self.assertIsNotNone(drop)
   result=s.handle(pickup(drop),2320);self.assertEqual(struct.unpack('>i',result[0].payload)[0],0)
 def test_dropped_regional_ingredients_feed_existing_crafting(self):
  from els_server.storage.manufacture import execute
  from els_server.domain.manufacture_requirements import requirements
  from els_server.domain.reward_rules import item_plan
  for mid,template,rid in ((34000,700245,79002),(34000,700246,79003),(34110,700247,79004),(34110,700248,79005)):
   app,room,members,npc=self.arrange(mid);s=members[0];s.world_drops={}
   # Real source/writer and native pickup; force this regional pool outcome.
   with patch('els_server.domain.ordinary_misc_loot.plans',return_value=[(template,1)]):s.handle(fixture.death(npc,s.account.uid),2400)
   self.pickup_all(s);demand=requirements(rid)
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE')
    for tid,qty in demand['materials'].items():
     if tid!=template:grant_items(db,[item_plan(tid,qty)],s.account.uid)
    db.execute('UPDATE reward_balances SET ed=100000 WHERE uid=?',(s.account.uid,))
   payload=struct.pack('>iiqI',rid,1,-1,0);operation='owned-regional-crafting:'+str(rid)
   before=s.account.get_inventory_snapshot();result=execute(self.path,s.account.uid,s.account.account_id,payload,operation,now=1000,authorize=lambda:True,prepare=lambda r:encode_event(Event(0x201,kind=0x199,payload=r['response'])))
   self.assertFalse(result['replayed']);self.assertEqual(result['audit']['rewards'],{rid:1})
   self.assertEqual(sum(i['count']for i in result['inventory']if i['template']==template),0)
   saved=s.account.get_inventory_snapshot();self.assertNotEqual(saved,before)
   again=execute(self.path,s.account.uid,s.account.account_id,payload,operation,now=1000,authorize=lambda:True)
   self.assertTrue(again['replayed']);self.assertEqual(saved,s.account.get_inventory_snapshot())
   DETAILS.append(dict(dropped_ingredient=template,craft_recipe=rid,output=rid,native_pickup=True,existing_craft_transaction=True,replay=True))
 def test_actual_start_preloads_misc_without_eager_ddl(self):
  import asyncio
  from els_server.application import Application
  from els_server.config import ServerConfig
  path=Path(self.tmp.name)/'owned-start.sqlite3';app=Application(ServerConfig(state_file=path,mode='local',accounts_file=Path(self.tmp.name)/'owned-auth.sqlite3'))
  rules.catalog.cache_clear()
  try:
   asyncio.run(app.start());self.assertEqual(rules.catalog.cache_info().currsize,1)
   with closing(sqlite3.connect(path))as db:self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='ordinary_misc_loot_issues'").fetchone())
  finally:app.close()
  DETAILS.append(dict(actual_Application_start=True,misc_catalog_prewarmed=True,eager_misc_DDL=False,isolated_own_state=True))
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Misc)
 if len(sys.argv)>1 and sys.argv[-1].startswith('test_'):suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[-1],Misc)
 output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
 manifest=W/'candidate-manifest.json'
 target=W/('results-'+str(time.time_ns())+'.json')
 target.write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),output=output.getvalue(),details=DETAILS,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),tester_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf8');print(output.getvalue());sys.exit(not result.wasSuccessful())
