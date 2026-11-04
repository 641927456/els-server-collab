import runtime_inputs
import hashlib,io,json,sqlite3,struct,sys,time,unittest,uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import verify_misc as original
from els_server.domain import ordinary_misc_loot as misc,regional_drop_materials as material
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_state import load_items,grant_items,InventoryFull
W=Path(__file__).resolve().parent;DETAILS=[]

def exchange_event(row,quantity=1,**changes):
 fields=dict(house=row['house'],uid=0,source=row['source'],source_quantity=1,destination=0,kind=1,quantity=quantity,flag=1,index=0);fields.update(changes)
 return Event(0x202,kind=0x223,performers=(0,),payload=struct.pack('>iQiiiiiBi',*fields.values()))

class Completion(unittest.TestCase):
 setUp=original.Misc.setUp
 party=original.Misc.party
 arrange=original.Misc.arrange
 hit=original.Misc.hit
 pickup_all=original.Misc.pickup_all
 case=original.Misc.case
 def count(self,s,template):return sum(i['count']for i in s.account.get_inventory_snapshot()['items']if i['template']==template)
 def reply(self,s,event,sequence,kind):
  result=s.handle(event,sequence);matches=[e for e in result if e.kind==kind];self.assertEqual(len(matches),1,[hex(e.kind)for e in result]);encode_event(matches[0]);return matches[0]
 def town(self,s,town):
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE location SET town=? WHERE uid=?',(town,s.account.uid))
  s.account.location=s.account.store.load();s.active_map=town;s.phase='town_ready';s.dungeon_run=None;s.dungeon_return_pending=False;s.gate_stage_loading=False;s.dungeon_substage_synced=False;s.town_warp_transition=None
 def dropped(self,mid=34510,party=False):
  app,room,members,npc=self.arrange(mid,boss=True,party=party)
  for s in members:s.world_drops={}
  self.hit(members[0],npc)
  for s in members:self.pickup_all(s)
  return members
 def seed(self,s,rows):
  from els_server.domain.reward_rules import item_plan
  from els_server.domain.raid_reward_items import _issue_source
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');plan=[item_plan(t,n)for t,n in rows]
   cap=_issue_source(db,s.account.uid,'owned-material-setup:'+str(uuid.uuid4()),'ordinary',dict(controlled_fixture=True),plan,lambda d:True)
   grant_items(db,plan,s.account.uid,raid_reward_source=cap)
 def test_solo_pruinaum_boss_actual_pickup_quantities(self):
  s=self.dropped()[0];self.assertEqual(self.count(s,711763),2);self.assertEqual(self.count(s,711785),1)
 def test_party_outskirts_boss_actual_pickup_quantities(self):
  members=self.dropped(34710,party=True)
  for s in members:self.assertEqual((self.count(s,711763),self.count(s,711785)),(2,1))
 def test_exact_region_scope_and_normal_monster(self):
  p=misc.catalog();self.assertEqual(sum(any(r['template']==711763 for r in m['extra_materials'])for m in p['maps'].values()),47)
  self.assertEqual(sum(any(r['template']==711785 for r in m['extra_materials'])for m in p['maps'].values()),7)
  for mid,wanted in((30092,set()),(34110,{711763}),(34510,{711763,711785}),(34760,{711763})):
   from types import SimpleNamespace as NS
   for boss in(False,True):
    rows=misc.plans(NS(c={'dungeon':mid},origin={'boss':boss},family=1),lambda n:0,0)
    got={t for t,n in rows if t in(711763,711785)}
    self.assertEqual(got,wanted if boss else wanted-{711763})
 def test_new_readers_remain_source_bound(self):
  from els_server.domain.reward_rules import item_plan
  from els_server.domain.raid_reward_items import source_only_templates
  for t in(711763,711785):
   self.assertIn(t,source_only_templates())
   with closing(sqlite3.connect(self.path))as db,db:
    with self.assertRaises(ValueError):grant_items(db,[item_plan(t,1)],self.a.uid)
 def test_dropped_giant_native_preview_use_cold_replay(self):
  s=self.dropped(34330)[0];self.town(s,20010);item=next(i for i in s.account.get_inventory_snapshot()['items']if i['template']==711763);before=self.count(s,701000)
  preview=Event(0x202,kind=0x559,performers=(0,),payload=struct.pack('>iIBB',711763,0,0,0));reply=self.reply(s,preview,3100,0x55a);self.assertEqual(struct.unpack_from('>i',reply.payload)[0],0)
  event=Event(0x202,kind=0x196,performers=(0,),payload=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0));reply=s.handle(event,3101)
  self.assertTrue(reply);self.assertEqual(self.count(s,701000)-before,100);self.assertEqual(self.count(s,711763),1)
  saved=s.account.get_inventory_snapshot();s.handle(event,3101);self.assertEqual(saved,s.account.get_inventory_snapshot())
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(sum(i['count']for i in load_items(db,s.account.uid)if i['template']==701000),before+100)
  DETAILS.append(dict(actual_native_giant_preview_use=True,source_consumed=1,magic_crystals_added=100,replay_and_cold_read=True))
 def test_all_original_npc_recipes_with_dropped_material(self):
  for index,row in enumerate(material.catalog()['recipes']):
   s=self.giant_dropped(34360 if row['source']==118191 else 34730)[0]if row['source']in(118191,118250)else self.dropped()[0]
   self.town(s,row['town']);before=self.count(s,row['destination']);event=exchange_event(row)
   reply=self.reply(s,event,3200+index,0x224);self.assertEqual(struct.unpack_from('>i',reply.payload)[0],0,(row,reply))
   self.assertEqual(self.count(s,row['destination'])-before,row['quantity']);saved=s.account.get_inventory_snapshot();s.handle(event,3200+index);self.assertEqual(saved,s.account.get_inventory_snapshot())
   DETAILS.append(dict(house=row['house'],town=row['town'],source=row['source'],destination=row['destination'],quantity=row['quantity'],actual_native_exchange=True,replay=True))
 def test_native_bulk_exchange_consumes_exact_owned_giant_count(self):
  s=self.dropped(34330)[0];row=next(r for r in material.catalog()['recipes']if r['source']==711763);self.town(s,row['town']);before=self.count(s,701000)
  reply=self.reply(s,exchange_event(row,quantity=2),3300,0x224);self.assertEqual(struct.unpack_from('>i',reply.payload)[0],0);self.assertEqual(self.count(s,711763),0);self.assertEqual(self.count(s,701000)-before,200)
 def test_exchange_wrong_scene_or_unowned_or_forged_quantity_rejected(self):
  s=self.dropped()[0];row=next(r for r in material.catalog()['recipes']if r['source']==711785);self.town(s,20000);saved=s.account.get_inventory_snapshot()
  self.assertEqual(struct.unpack_from('>i',self.reply(s,exchange_event(row),3400,0x224).payload)[0],-1);self.assertEqual(saved,s.account.get_inventory_snapshot())
  self.town(s,row['town'])
  for i,event in enumerate((exchange_event(row,quantity=2),exchange_event(row,source_quantity=0),exchange_event(row,destination=118178))):
   self.assertEqual(struct.unpack_from('>i',self.reply(s,event,3401+i,0x224).payload)[0],-1);self.assertEqual(saved,s.account.get_inventory_snapshot())
 def test_exchange_encoding_failure_and_full_bag_do_not_consume(self):
  s=self.dropped()[0];row=next(r for r in material.catalog()['recipes']if r['source']==711785);self.town(s,row['town']);saved=s.account.get_inventory_snapshot();event=exchange_event(row)
  for i,(target,error)in enumerate((('els_server.storage.material_exchange.encode_event',ValueError('owned-encode')),('els_server.storage.material_exchange.grant_items',InventoryFull('owned-full')))):
   with patch(target,side_effect=error):self.assertEqual(struct.unpack_from('>i',self.reply(s,event,3500+i,0x224).payload)[0],-1)
   self.assertEqual(saved,s.account.get_inventory_snapshot())
  self.assertEqual(struct.unpack_from('>i',self.reply(s,event,3502,0x224).payload)[0],0)
 def test_existing_purifier_writer_reuses_shared_transaction(self):
  from els_server.storage.purifier_exchange import exchange
  s=self.s;self.seed(s,[(136115,7)]);self.town(s,20013);payload=struct.pack('>iQiiiiiBi',40272,0,136115,7,136109,3,1,1,0)
  result=exchange(self.path,s.account.uid,20013,payload,'owned-old-purifier',account_id=s.account.account_id,now=2000000000)
  self.assertEqual(struct.unpack_from('>i',result[0].payload)[0],0);self.assertEqual(self.count(s,136115),0);self.assertEqual(self.count(s,136109),1)
  saved=s.account.get_inventory_snapshot();exchange(self.path,s.account.uid,20013,payload,'owned-old-purifier',account_id=s.account.account_id,now=2000000000);self.assertEqual(saved,s.account.get_inventory_snapshot())
 def test_all_53_raid_final_phase_weekly_repeat_and_receipt(self):
  from els_server.domain import formal_raid_economy as rules
  from els_server.storage import raid_economy_state as state
  from els_server.domain.raid_reward_items import _issue_source
  other=self.a.characters.create('RaidPeer',1,'owned-raid-material-peer')['uid'];a=self.a.for_character(other);a.enable_rewards();a.get_inventory_snapshot();owners=(self.a.uid,other)
  checked=0
  with closing(sqlite3.connect(self.path))as db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
   for mid,d in rules.policy()['maps'].items():
    db.execute('SAVEPOINT raid_map');mid=int(mid);last=max(map(int,d['phases']));epoch=str(uuid.uuid4())
    def contexts(epoch,stage):
     return[dict(owner=uid,run=str(uuid.uuid5(uuid.UUID(epoch),'reward:'+str(uid))),source_run=epoch,dungeon=mid,stage=stage,part=0,visits=stage+1,graph_sha256=d['graph_sha256'],proof=hashlib.sha256(f'{mid}:{stage}'.encode()).hexdigest(),alive=True,phase_experience=1,experience_bp=10000)for uid in owners]
    for stage in sorted(map(int,d['phases'])):
     rows=state.prepare_batch(db,contexts(epoch,stage),1793782000,lambda writer:True)
     for result in rows:
      got={p['template']:p['quantity']for p in result['items']if p['template']in(711763,711785)}
      self.assertEqual(got,dict(material.raid_items(mid))if stage==last else{})
    old=state.prepare_batch(db,contexts(epoch,last),1793782000,lambda writer:True);self.assertTrue(all(r['replayed']for r in old))
    later=str(uuid.uuid4());again=state.prepare_batch(db,contexts(later,last),1793782000,lambda writer:True)
    self.assertTrue(all(not r['first']for r in again))
    for result in again:
     plans=[p for p in result['items']if p['template']in(711763,711785)];self.assertEqual({p['template']:p['quantity']for p in plans},dict(material.raid_items(mid)))
     cap=_issue_source(db,result['owner'],result['run'],'phase',result['source'],plans,lambda writer:True);grant_items(db,plans,result['owner'],raid_reward_source=cap)
     self.assertEqual(sum(i['count']for i in load_items(db,result['owner'])if i['template']==711763),2)
    checked+=1;db.execute('ROLLBACK TO raid_map');db.execute('RELEASE raid_map')
   db.rollback()
  DETAILS.append(dict(raid_maps=checked,members=2,final_phase_only=True,weekly_and_repeat=True,immutable_phase_replay=True,controlled_state_and_factory=True))
 def test_actual_raid_native_clear_rollback_cold_read_and_replay(self):
  s=original.fixture.SecondBatch.dungeon(self,35370)
  from els_server.domain.region_quests import region_catalog
  with closing(sqlite3.connect(self.path))as db,db:
   for qid in region_catalog().data['quests']:db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(s.account.uid,int(qid),1000,'{}'))
  fault=False;seen=[]
  for _ in range(25):
   run=s.dungeon_run;cursor=(run.stage,run.part,run.visits);self.assertNotIn(cursor,seen);seen.append(cursor)
   for npc in tuple(run.current['npcs']):
    if npc.get('team',1)==0:continue
    reply=s.handle(original.fixture.death(npc,s.account.uid),3600+npc['key']);self.assertIn(0xae,[e.kind for e in reply],(cursor,npc['template'],[hex(e.kind)for e in reply]))
   if any(c['kind']==5 for c in run.current['conditions']):s.handle(Event(0x202,kind=0xb8,payload=struct.pack('>b',run.part)),3690)
   self.t[0]+=100000;s.next_periodic=0;s.periodic_notifications();self.assertTrue(s.part_end_notified,(cursor,run.next))
   event=original.fixture.bb(s)
   if run.next['kind']==4:
    with closing(sqlite3.connect(self.path))as db:before=list(db.iterdump())
    from els_server.protocol.protocol_codec import encode_event as encoder
    def fail(e):
     if e.kind==0xc1:raise RuntimeError('owned-raid-final-encode')
     return encoder(e)
    with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail):
     with self.assertRaisesRegex(RuntimeError,'owned-raid-final-encode'):s.handle(event,3700)
    with closing(sqlite3.connect(self.path))as db:self.assertEqual(before,list(db.iterdump()))
    self.assertIs(s.dungeon_run,run);fault=True
   reply=s.handle(event,3701)
   if s.clear_notified:
    self.assertIn(0xc1,[e.kind for e in reply]);self.assertTrue(fault);self.assertEqual(self.count(s,711763),2)
    saved=s.account.get_inventory_snapshot();s.handle(event,3701);self.assertEqual(saved,s.account.get_inventory_snapshot())
    with closing(sqlite3.connect(self.path))as db:self.assertEqual(sum(i['count']for i in load_items(db,s.account.uid)if i['template']==711763),2)
    DETAILS.append(dict(actual_raid_map=35370,original_AD_BB_C1=True,phases=len(seen),final_encoding_rollback=True,cold_read_and_replay=True));return
   if s.gate_stage_loading:s.handle(Event(0x202,performers=(0,),kind=0xb3,payload=bytes(9)),3710)
  self.fail('Actual native raid did not complete')
 def test_bulk_output_over_one_factory_plan_count(self):
  s=self.s;self.seed(s,[(711763,20)]);row=next(r for r in material.catalog()['recipes']if r['source']==711763);self.town(s,row['town']);before=self.count(s,701000)
  reply=self.reply(s,exchange_event(row,quantity=20),3800,0x224);self.assertEqual(struct.unpack_from('>i',reply.payload)[0],0);self.assertEqual(self.count(s,711763),0);self.assertEqual(self.count(s,701000)-before,2000)
 def test_exchange_lease_revoked_after_encoding_rolls_back(self):
  s=self.dropped()[0];row=next(r for r in material.catalog()['recipes']if r['source']==711785);self.town(s,row['town']);saved=s.account.get_inventory_snapshot();generation=s.shop_session_id
  from els_server.storage.material_exchange import encode_event as encoder
  def revoke(event):
   result=encoder(event);s.shop_session_id=str(uuid.uuid4());return result
  try:
   with patch('els_server.storage.material_exchange.encode_event',side_effect=revoke):self.assertNotIn(0x224,[e.kind for e in s.handle(exchange_event(row),3900)])
  finally:s.shop_session_id=generation
  self.assertEqual(saved,s.account.get_inventory_snapshot())
 def giant_dropped(self,mid,party=False,prepare_only=False):
  app,room,members,npc=self.arrange(mid,boss=True,party=party)
  from els_server.domain.dungeon_routes import DungeonRun
  from els_server.domain.friends_spawns import capture_static_origin
  last=material.catalog()['giant_maps'][str(mid)]['final_stage']
  for s in members:
   run=s.dungeon_run;run._load_stage(last);run.part=next(k for k,p in run.parts.items()if any(n['boss']and n['active']and not n['no_drop']for n in p['npcs']));run.loaded();s.gate_stage=last;s.defeated_npcs=run.defeated;s.world_drops={}
  if room is not None:capture_static_origin(room)
  npc=next(n for n in members[0].dungeon_run.current['npcs']if n['boss']and n['active']and not n['no_drop'])
  if prepare_only:return app,room,members,npc
  reply=self.hit(members[0],npc);self.assertIn(0xcf,[e.kind for e in reply])
  for s in members:self.pickup_all(s)
  return members
 def test_giant_solo_all_current_display_families_and_large_bundle(self):
  for mid,box,target,count in((34360,118191,118178,10000),(34730,118250,118206,50)):
   previous=(self.count(self.s,711763),self.count(self.s,135911))
   s=self.giant_dropped(mid)[0];self.assertEqual(self.count(s,711763)-previous[0],2);self.assertEqual(self.count(s,box),1);self.assertEqual(self.count(s,135911)-previous[1],1)
   self.town(s,20010);item=next(i for i in s.account.get_inventory_snapshot()['items']if i['template']==box);before=self.count(s,target)
   preview=Event(0x202,kind=0x559,performers=(0,),payload=struct.pack('>iIBB',box,0,0,0));self.assertEqual(struct.unpack_from('>i',self.reply(s,preview,4000+mid,0x55a).payload)[0],0)
   event=Event(0x202,kind=0x196,performers=(0,),payload=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0));s.handle(event,4100+mid)
   self.assertEqual(self.count(s,target)-before,count);self.assertEqual(self.count(s,box),0);saved=s.account.get_inventory_snapshot();s.handle(event,4100+mid);self.assertEqual(saved,s.account.get_inventory_snapshot())
 def giant_party(self,mid,box):
  for s in self.giant_dropped(mid,party=True):self.assertEqual(self.count(s,711763),2);self.assertEqual(self.count(s,box),1);self.assertEqual(self.count(s,135911),1)
 def test_giant_party_nigmore(self):self.giant_party(34360,118191)
 def test_giant_party_outskirts(self):self.giant_party(34730,118250)
 def test_giant_party_late_encoding_rolls_back_drops_and_quests(self):
  from els_server.domain.giant_misc_loot import group_death
  app,room,members,npc=self.giant_dropped(34730,party=True,prepare_only=True);before=[s.account.get_inventory_snapshot()for s in members]
  with closing(sqlite3.connect(self.path))as db:dump=list(db.iterdump())
  with patch('els_server.domain.party_commands._prepared_boxes',side_effect=ValueError('owned-giant-late-encode')):
   with self.assertRaisesRegex(ValueError,'owned-giant-late-encode'):group_death(app.world.dungeons,room,members[0],original.fixture.death(npc,members[0].account.uid))
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(dump,list(db.iterdump()))
  self.assertEqual(before,[s.account.get_inventory_snapshot()for s in members]);self.assertTrue(all(not s.dungeon_run.defeated and not s.world_drops for s in members))
 def test_change_material_new_source_cannot_escape_exact_giant_map(self):
  from els_server.domain.raid_reward_items import _issue_source
  from els_server.domain.reward_rules import item_plan
  for mid,template in((34330,135911),(34360,136174)):
   graph=material.catalog()['giant_maps'].get(str(mid),material.catalog()['giant_maps']['34360'])
   proof=dict(reward_source=misc.POLICY,context=dict(dungeon=mid,stage=graph['final_stage'],graph_sha256=graph['graph_sha256']),origin=dict(boss=True))
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE');plan=[item_plan(template,1)];cap=_issue_source(db,self.a.uid,'owned-bad-giant-source:'+str(mid),'ordinary',proof,plan,lambda writer:True)
    with self.assertRaisesRegex(ValueError,'Giant Change material original source'):grant_items(db,plan,self.a.uid,raid_reward_source=cap)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Completion)
 if len(sys.argv)>1:suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[-1],Completion)
 out=io.StringIO();result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
 target=W/('completion-results-'+str(time.time_ns())+'.json');target.write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),output=out.getvalue(),details=DETAILS,manifest_sha256=hashlib.sha256((W/'candidate-manifest.json').read_bytes()).hexdigest(),tester_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf8');print(out.getvalue());sys.exit(not result.wasSuccessful())
