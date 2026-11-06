"""Source-qualified visible retirement regressions; controlled state, no player data."""
import argparse,ast,atexit,copy,hashlib,importlib.util,json,os,shutil,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
p=argparse.ArgumentParser();p.add_argument('--baseline',action='store_true');p.add_argument('--only');p.add_argument('--runtime',required=True,type=Path)
args=p.parse_args();sys.path.insert(0,str(args.runtime.resolve()))
if not args.baseline:
 import els_server.domain
 els_server.domain.__path__.insert(0,str(HERE/'candidate/els_server/domain'))
saved=sys.argv;sys.argv=['fixtures','--runtime',str(args.runtime)]
spec=importlib.util.spec_from_file_location('retirement_fixtures',ROOT/'analysis/atlas-mine-gate-20261101-v1/verify_retirements.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);sys.argv=saved
from els_server.domain import dungeon_flow as flow,scene_actor_retirements as scenes
from els_server.domain.dungeon_lifecycle import death_report
from els_server.protocol.protocol_codec import Event,encode_event
manifest=json.loads((HERE/'candidate-manifest.json').read_bytes());RULES=manifest['new_rules'];BASELINE=[]
if not args.baseline:
 from els_server.domain.dungeon_routes import RouteCatalog,route_catalog
 directory=tempfile.TemporaryDirectory(prefix='catalog-fixture-',dir=HERE);atexit.register(directory.cleanup)
 catalog_path=Path(directory.name)
 os.link(args.runtime.resolve()/'els_server/data/client/dungeon_routes.json',catalog_path/'dungeon_routes.json')
 shutil.copyfile(HERE/'candidate/els_server/data/client/dungeon_routes.manifest.json',catalog_path/'dungeon_routes.manifest.json')
 checked=RouteCatalog(catalog_path);selected=route_catalog();assert checked._data==selected._data;selected.manifest=checked.manifest

base_fixture=h.fixture
def fixture(rule,**kw):
 s,n,e=base_fixture(rule,**kw);run=s.dungeon_run
 # Keep other source-defined exits unreported. Never let a parallel exit
 # mask the missing selected controller (Solace branches and castle hub).
 for c in run.current['conditions']:
  if c['kind']==3 and n['template']not in c['required']:
   for other in run.current['npcs']:
    if other['template']in c['required']:run.defeated.pop(other['key'],None)
 return s,n,e
h.fixture=fixture

def identity(rule):return(rule['dungeon'],rule['stage'],rule['part'],rule['source']['source_index'])
def event_for(n):return Event(0x202,performers=(0,),kind=0xad,payload=h.native255(n['key'],n['hp']))
class VisibleRetirements(unittest.TestCase):
 def test_every_source_original_gate_delay_and_replay(self):
  for rule in RULES:
   with self.subTest(source=identity(rule)):
    s,n,e=fixture(rule);run=s.dungeon_run
    self.assertFalse(run.poll_ready())
    with patch('els_server.domain.quest_flow.store',side_effect=AssertionError('quest write')),patch('els_server.domain.dungeon_equipment_loot_flow.accepted_death',side_effect=AssertionError('loot write')),patch('els_server.domain.legacy_pve_exp.accepted_death',side_effect=AssertionError('EXP write')):
     reply=flow.handle(s,e)
     if args.baseline:
      self.assertEqual(reply,[]);self.assertNotIn(n['key'],run.defeated);self.assertFalse(run.poll_ready())
      BASELINE.append(dict(source=identity(rule),template=n['template'],replies=[],gate_ready=False));continue
     if any(c['kind']==5 for c in run.current['conditions']):
      self.assertEqual([r.kind for r in reply],[0xae,0xaf]);self.assertFalse(s.part_end_notified)
      portal=flow.handle(s,Event(0x202,kind=0xb8,payload=struct.pack('>b',run.part)))
      self.assertEqual([r.kind for r in portal],[0xb9]);self.assertEqual(portal[0].payload,bytes(4))
     ready=[c for c in run.current['conditions']if run.condition_ready(c)];self.assertEqual(len(ready),1)
     delay=ready[0]['delay']
     if delay:
      self.assertEqual([r.kind for r in reply],[0xae,0xaf]);self.assertFalse(s.part_end_notified)
      s.test_clock[0]=delay-0.001;self.assertEqual(flow.periodic(s),[])
      s.test_clock[0]=delay;reply+=flow.periodic(s)
     self.assertEqual([r.kind for r in reply],[0xae,0xaf,0xba]);self.assertTrue(s.part_end_notified)
     self.assertEqual([r.kind for r in flow.handle(s,e)],[0xae]);self.assertFalse(n['active']);self.assertFalse(s.clear_notified);self.assertFalse(s.world_drops)
     for r in reply:encode_event(r)
 def test_source_contract_and_prior_rules(self):
  from els_server.domain.scene_retirement_sources import RULES as actual
  old=ast.parse((args.runtime/'els_server/domain/scene_retirement_sources.py').read_text(encoding='utf8'))
  new=ast.parse((HERE/'candidate/els_server/domain/scene_retirement_sources.py').read_text(encoding='utf8'))
  self.assertEqual(ast.dump(ast.Module(body=new.body[:-1],type_ignores=[])),ast.dump(old))
  self.assertEqual(len(actual),manifest['previous_rules']+len(RULES))
  for name,sha in manifest['outputs'].items():self.assertEqual(hashlib.sha256((HERE/'candidate'/name).read_bytes()).hexdigest(),sha)
  self.assertTrue(all('native_class'in r for r in RULES))
  self.assertEqual(len({json.dumps(r,sort_keys=True)for r in RULES}),len(RULES))
  self.assertEqual(len([r for r in RULES if r['source']['template']==2154]),4)
 def test_full_clear_keeps_remaining_hostiles(self):
  tested=0
  for rule in RULES:
   s,n,e=fixture(rule,all_others_defeated=False);run=s.dungeon_run
   if not any(c['kind']in (0,5)for c in run.current['conditions']):continue
   # An opening scene may be the sole active actor. That is the positive
   # last-actor case above, not an uncleared-hostile fixture.
   remaining=[x for x in run.current['npcs']if x is not n and x['active']and x.get('team',1)!=0 and x['key']not in run.defeated]
   if not remaining:continue
   self.assertEqual([r.kind for r in flow.handle(s,e)],[0xae,0xaf]);self.assertFalse(s.part_end_notified)
   self.assertTrue(any(x['active']and x['key']not in run.defeated for x in run.current['npcs']));tested+=1
  self.assertGreater(tested,0)
 def test_source_hp_lease_generation_and_conflicting_report_rejected(self):
  for script in manifest['scripts']:
   rule=next(r for r in RULES if r['script']==script)
   for change in ('source','point','class','script','graph','hp','lease','epoch','phase','roster','owner','status','killer','repeat'):
    with self.subTest(script=script,change=change):
     s,n,e=fixture(rule);run=s.dungeon_run
     if change=='source':n['source_index']+=1000
     if change=='point':n['start_point']+=1000
     if change=='script':
      run.catalog=copy.copy(run.catalog);run.catalog.manifest=copy.deepcopy(run.catalog.manifest);run.catalog.manifest['source_sha256'][script]='0'*64
     if change=='graph':run.graph['source_sha256']='0'*64
     if change=='hp':n['hp']+=1
     if change=='lease':s.application.playing[71]=object()
     if change=='epoch':s.reward_run_id='wrong-run'
     if change=='phase':s.phase='town_ready'
     if change=='roster':s.dungeon_participants=frozenset((1001,1002))
     if change=='owner':e=Event(0x202,performers=(0,),kind=0xad,payload=h.native255(n['key'],n['hp'],owner=9999))
     raw=bytearray(e.payload)
     if change=='status':raw[45]=0
     if change=='killer':struct.pack_into('>Q',raw,13,1001)
     if change in ('status','killer'):e=Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
     if change=='repeat':
      flow.handle(s,e);raw=bytearray(e.payload);struct.pack_into('>f',raw,21,1.)
      e=Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
     before=dict(run.defeated)
     if change=='class':
      from els_server.game_data import client_data
      original=client_data().npc
      def altered(identity):
       value=original(identity)
       if identity==n['template']:value['class_id']=103 if rule['native_class']!=103 else 0
       return value
      with patch.object(client_data(),'npc',side_effect=altered):reply=flow.handle(s,e)
     else:reply=flow.handle(s,e)
     self.assertIn(reply,([],None));self.assertEqual(run.defeated,before)
 def test_shared_original_generation_master_delivery_and_retry(self):
  for rule in RULES:
   with self.subTest(source=identity(rule)):
    dispatcher,room,members,e=h.shared_fixture(rule)
    self.assertEqual(dispatcher.death(room,members[1],e),[])
    reply=dispatcher.death(room,members[0],e);self.assertEqual([r.kind for r in reply][:2],[0xae,0xaf])
    self.assertEqual([r.kind for r in members[1].mailbox.messages],[r.kind for r in reply if r.kind!=0xae])
    for m in members:self.assertIn(death_report(e.payload)['index'],m.dungeon_run.defeated)
    count=len(members[1].mailbox.messages);self.assertEqual([r.kind for r in dispatcher.death(room,members[0],e)],[0xae]);self.assertEqual(len(members[1].mailbox.messages),count)
 def test_no_partial_state_on_encode_or_mailbox_failure(self):
  for script in manifest['scripts']:
   rule=next(r for r in RULES if r['script']==script)
   s,n,e=fixture(rule);run=s.dungeon_run;before=(dict(run.defeated),run.next,run.ready_at,n['active'],s.part_end_notified)
   with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('controlled encoder failure')):
    with self.assertRaisesRegex(RuntimeError,'controlled encoder failure'):flow.handle(s,e)
   self.assertEqual((run.defeated,run.next,run.ready_at,n['active'],s.part_end_notified),before)
   dispatcher,room,members,e=h.shared_fixture(rule);old=[dict(m.dungeon_run.defeated)for m in members]
   from els_server.domain.local_session import SessionOrderError
   for _ in range(256):members[1].mailbox.append(Event(0x201,kind=0xb9,payload=bytes(4)))
   with self.assertRaises(SessionOrderError):dispatcher.death(room,members[0],e)
   self.assertEqual([m.dungeon_run.defeated for m in members],old)
 def test_ordinary_reports_remain_on_original_dispatch(self):
  for rule in RULES:
   s,n,e=fixture(rule);dispatcher,room,members,shared=h.shared_fixture(rule)
   for flag in (0,1):
    for original,call in ((e,lambda ev:scenes.handle(s,ev,death_report(ev.payload))),(shared,lambda ev:scenes.shared_retirement(dispatcher,room,members[0],ev))):
     raw=bytearray(original.payload);raw[4]=flag
     self.assertIsNone(call(Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))))
 def test_fork_selects_only_the_reported_original_exit(self):
  rules=[r for r in RULES if (r['dungeon'],r['stage'],r['part'])in ((33891,0,1),(35080,0,0))]
  self.assertEqual(len(rules),5)
  for rule in rules:
   s,n,e=fixture(rule);run=s.dungeon_run
   expected=next(c['next']for c in run.current['conditions']if c['kind']==3 and n['template']in c['required'])
   self.assertEqual([r.kind for r in flow.handle(s,e)],[0xae,0xaf,0xba]);self.assertIn(run.next,expected)
   self.assertTrue(all(x['key']not in run.defeated for x in run.current['npcs']if x['key']!=n['key']and x['template']in (2388,2389,8827,8828,8829,8832)))
if args.only:suite=unittest.TestSuite(VisibleRetirements(n)for n in args.only.split(','))
elif args.baseline:suite=unittest.TestSuite([VisibleRetirements('test_every_source_original_gate_delay_and_replay')])
else:suite=unittest.defaultTestLoader.loadTestsFromTestCase(VisibleRetirements)
result=unittest.TextTestRunner(verbosity=2).run(suite)
out=dict(ok=result.wasSuccessful(),runtime=str(args.runtime.resolve()),baseline=args.baseline,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),rules=len(RULES),baseline_sources=BASELINE,failure_details=[str(t)+'\n'+d for t,d in result.failures+result.errors],natural_GUI=False,natural_combat=False,actual_player_database=False)
(HERE/('baseline-result.json'if args.baseline else 'candidate-retest-result.json'if args.only else 'candidate-result.json')).write_text(json.dumps(out,indent=2),encoding='utf8');sys.exit(not result.wasSuccessful())
