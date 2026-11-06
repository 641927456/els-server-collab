"""Current resource regression of the native condition request and existing gates."""
import argparse,copy,json,struct,sys,unittest,uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;ROOT=Path('G:/els')
parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
RUNTIME=ROOT/'releases/local/local-native-atlas-scroll-support-20261101-v1'
sys.path[:0]=[str(RUNTIME),str(ROOT/'analysis/cobodex-dungeons-audit-20261031-v1/live-check/expiry-source/tests')]
if not args.baseline:
 import els_server.domain
 els_server.domain.__path__.insert(0,str(HERE/'candidate/els_server/domain'))
from els_server.domain import dungeon_flow as flow
from els_server.domain.dungeon_routes import DungeonRun,route_catalog
from els_server.domain.dungeon_clock import DungeonClock
from els_server.protocol.protocol_codec import Event
from test_lithia_memory8_offfield_expiry import session
SEED='00000000-0000-4000-8000-000000000001'
proof=json.loads((HERE.parent/'native-proof.json').read_bytes());assert proof['ok']

def fixture(stage=1,part=2,identity=33342):
 run=DungeonRun(identity,SEED,internal=True);run._load_stage(stage);run.part=part
 clock=[0.0];run.clock=lambda:clock[0];run.loaded()
 s=session(run,part_end_notified=False);s.dungeon_clock=DungeonClock()
 s.gate_stage_loading=False;s.gate_stage=stage;s.previous_dungeon_part=None
 s.summon_deaths={};s.summon_requests={};s.summon_next_key=16;s.dungeon_failed=False
 return s,clock

def cleared(s):
 run=s.dungeon_run
 run.defeated={n['key']:b'explicit previously accepted combat fixture'for n in run.current['npcs']if n['active']}
 s.defeated_npcs=run.defeated

def report(s,flags=None):
 run=s.dungeon_run
 flags=flags if flags is not None else [1]*len(run.current['conditions'])
 raw=struct.pack('>iiHI',run.stage,run.part,0,len(flags))+bytes(flags)+b'\0'
 if (run.stage,run.part)in((1,2),(2,3))and flags==[1]:
  assert raw==bytes.fromhex(proof['request_hex'][0 if run.stage==1 else 1])
 return Event(0x202,performers=(0,),kind=0x471,payload=raw)

def state(s):
 r=s.dungeon_run
 return (r.stage,r.part,r.visits,copy.deepcopy(r.defeated),copy.deepcopy(r.next),r.ready_at,r.portal_requested,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started)

class ConditionTests(unittest.TestCase):
 def test_baseline_or_original_city_sequence_to_next_world(self):
  s,t=fixture();run=s.dungeon_run;cleared(s)
  self.assertEqual(flow.periodic(s),[]);before=state(s)
  e=report(s);reply=flow.handle(s,e)
  if args.baseline:
   self.assertIsNone(reply);self.assertEqual(state(s),before);return
  self.assertEqual([e.kind for e in reply],[0x472]);self.assertEqual(struct.unpack('>7i',reply[0].payload),(0,1,0,1,2,0,0))
  self.assertTrue(run.portal_requested);self.assertFalse(s.part_end_notified)
  ready=run.ready_at
  t[0]=1.;self.assertEqual([e.kind for e in flow.handle(s,e)],[0x472]);self.assertEqual(run.ready_at,ready)
  t[0]=1.999;self.assertEqual(flow.periodic(s),[])
  t[0]=2.;self.assertEqual([e.kind for e in flow.periodic(s)],[0xba])
  self.assertEqual([e.kind for e in flow.handle(s,Event(0x202,kind=0xbb,payload=b'\2'))],[0xbc,0xb2])
  self.assertEqual((run.stage,run.part),(2,0));self.assertFalse(run.portal_requested)

 def test_city_empty_portal_to_original_boss(self):
  s,t=fixture(2,3);self.assertEqual(s.dungeon_run.current['npcs'],[])
  self.assertEqual(flow.periodic(s),[])
  self.assertEqual([e.kind for e in flow.handle(s,report(s))],[0x472]);t[0]=.999
  self.assertEqual(flow.periodic(s),[]);t[0]=1.
  self.assertEqual([e.kind for e in flow.periodic(s)],[0xba])
  self.assertEqual([e.kind for e in flow.handle(s,Event(0x202,kind=0xbb,payload=b'\3'))],[0xbc,0xb2])
  self.assertEqual((s.dungeon_run.stage,s.dungeon_run.part),(3,0))
  self.assertIn(2120,[n['template']for n in s.dungeon_run.current['npcs']])

 def test_early_wrong_or_unauthorized_report_never_opens(self):
  for change in ('enemy_alive','no_contact','truncated','count','bool','reserved','flag','stage','part','performer','uid','target','mode','lease','transaction','loading','failed'):
   with self.subTest(change=change):
    s,t=fixture();cleared(s);e=report(s);raw=bytearray(e.payload)
    if change=='enemy_alive':s.dungeon_run.defeated.pop(next(n['key']for n in s.dungeon_run.current['npcs']if n['active']))
    if change=='no_contact':raw[14]=0
    if change=='truncated':raw=raw[:-1]
    if change=='count':struct.pack_into('>I',raw,10,2000000000)
    if change=='bool':raw[14]=2
    if change=='reserved':raw[9]=1
    if change=='flag':raw[-1]=1
    if change=='stage':struct.pack_into('>i',raw,0,2)
    if change=='part':struct.pack_into('>i',raw,4,1)
    e=Event(0x202,performers=(1,)if change=='performer'else(0,),kind=0x471,payload=bytes(raw),
     uid=1001 if change=='uid'else 2**64-1,target_uid=1001 if change=='target'else 2**64-1,payload_mode=1 if change=='mode'else 0)
    if change=='lease':s.application.playing[71]=object()
    if change=='transaction':s.reward_transaction=object()
    if change=='loading':s.dungeon_substage_synced=False
    if change=='failed':s.dungeon_failed=True
    before=state(s);out=flow.handle(s,e)
    self.assertEqual(struct.unpack('>i',out[0].payload[:4])[0],-1)
    self.assertEqual(state(s),before)

 def test_encoding_failure_preserves_request_gate_and_clock(self):
  for kind in (0x472,0xba):
   s,t=fixture(2,3);cleared(s)
   if kind==0xba:s.dungeon_run.current['conditions'][0]['delay']=0
   before=state(s)
   from els_server.protocol.protocol_codec import encode_event
   def encode(e):
    if e.kind==kind:raise RuntimeError('isolated encoding failure')
    return encode_event(e)
   with patch('els_server.protocol.protocol_codec.encode_event',side_effect=encode):
    with self.assertRaisesRegex(RuntimeError,'isolated encoding failure'):flow.handle(s,report(s))
   self.assertEqual(state(s),before)

 def test_other_source_portals_use_same_handler(self):
  count=0
  for identity in (33332,33352,32982):
   graph=route_catalog().graph(identity)
   for stage,st in graph['stages'].items():
    for part,room in st['parts'].items():
     if not any(c['kind']==5 for c in room['conditions']):continue
     s,t=fixture(int(stage),int(part),identity);cleared(s)
     self.assertEqual(flow.periodic(s),[])
     self.assertEqual(struct.unpack_from('>i',flow.handle(s,report(s))[0].payload)[0],0)
     self.assertTrue(s.dungeon_run.portal_requested);count+=1
  self.assertGreaterEqual(count,4)

 def test_normal_clear_still_uses_existing_target(self):
  s,t=fixture(1,0);cleared(s)
  self.assertEqual([e.kind for e in flow.periodic(s)],[0xba]);target=dict(s.dungeon_run.next)
  self.assertEqual([e.kind for e in flow.handle(s,report(s))],[0x472]);self.assertEqual(s.dungeon_run.next,target)

 def test_curtain_request_is_not_a_portal_contact(self):
  s,t=fixture();cleared(s);before=state(s)
  self.assertEqual([e.kind for e in flow.handle(s,Event(0x202,kind=0xb8,payload=b'\2'))],[0xb9])
  self.assertEqual(state(s),before)
  self.assertEqual(flow.handle(s,Event(0x202,kind=0xbb,payload=b'\2')),[])

 def test_group_master_and_member_share_original_gate(self):
  dispatcher,room,members=group_fixture();master,member=members
  before=[state(m)for m in members]
  self.assertEqual([e.kind for e in dispatcher.condition_clear(room,member,report(member))],[0x472])
  self.assertEqual([state(m)for m in members],before)
  result=dispatcher.condition_clear(room,master,report(master))
  self.assertEqual([e.kind for e in result],[0x472]);self.assertEqual([e.kind for e in member.mailbox.drain()],[0x472])
  self.assertTrue(all(m.dungeon_run.portal_requested for m in members))
  self.assertEqual([m.dungeon_run.ready_at for m in members],[2.,2.])
  for m in members:m.test_clock[0]=2.;self.assertEqual([e.kind for e in flow.periodic(m)],[0xba])
  dispatcher.part_wait(room);self.assertEqual(room.phase,'part_end')

 def test_group_generation_mailbox_or_encoder_failure_is_atomic(self):
  from els_server.domain.local_session import SessionOrderError
  for change in ('generation','member_enemy','mailbox','encode'):
   dispatcher,room,members=group_fixture();master,member=members
   if change=='generation':member.dungeon_run.visits+=1
   if change=='member_enemy':member.dungeon_run.defeated.clear()
   if change=='mailbox':
    for _ in range(256):member.mailbox.append(Event(0x201,kind=1,payload=b'x'))
   before=[state(m)for m in members];queued=tuple(member.mailbox.messages)
   if change=='encode':
    with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('isolated encode')):
     with self.assertRaises(RuntimeError):dispatcher.condition_clear(room,master,report(master))
   elif change=='mailbox':
    with self.assertRaises(SessionOrderError):dispatcher.condition_clear(room,master,report(master))
   else:
    out=dispatcher.condition_clear(room,master,report(master))
    self.assertTrue(not out or struct.unpack_from('>i',out[0].payload)[0]==-1)
   self.assertEqual([state(m)for m in members],before);self.assertEqual(tuple(member.mailbox.messages),queued)

class Member(NS):__hash__=object.__hash__

def group_fixture(stage=1,part=2,identity=33342):
 from els_server.domain.friends_dungeon import FriendsDungeons,Room
 from els_server.domain.friends_world import Mailbox
 from els_server.domain.friends_spawns import capture_static_origin
 world=NS(party_of={},members={});dispatcher=FriendsDungeons(world)
 app=NS(playing={},accounts={},world=world,registry=NS(enabled=lambda _:True));members=[]
 for i in range(2):
  s,t=fixture(stage,part,identity);cleared(s);m=Member(**vars(s));m.test_clock=t;m.application=app
  a=m.account;a.uid=1001+i;a.account_id=71+i;a.store.uid=a.uid;a.root.character_accounts={a.uid:a}
  m.identity={'id':a.account_id};app.playing[a.account_id]=m;app.accounts[a.account_id]=a.root
  m.dungeon_participants=frozenset((1001,1002));m.shop_session_id='isolated-'+str(i)
  m.coop_error=False;m.social_overflow=False;m.mailbox=Mailbox()
  m.reward_run_id=str(uuid.uuid5(uuid.UUID(SEED),'reward:'+str(a.uid)));members.append(m)
 members=tuple(members);party=dict(members=members,leader=members[0]);room=Room(party,members,members[0],identity,SEED,phase='active');party['run']=room
 for m in members:world.party_of[m]=party;dispatcher.rooms[m]=room
 capture_static_origin(room);return dispatcher,room,members

if __name__=='__main__':
 suite=unittest.TestSuite([ConditionTests('test_baseline_or_original_city_sequence_to_next_world')])if args.baseline else unittest.defaultTestLoader.loadTestsFromTestCase(ConditionTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 out=dict(ok=result.wasSuccessful(),tests=result.testsRun,skipped=len(result.skipped),baseline=args.baseline,native_proof=str(HERE.parent/'native-proof.json'),natural_GUI=False,natural_combat=False,
  failures=[str(t)+'\n'+details for t,details in result.failures+result.errors])
 (HERE/('baseline-result.json'if args.baseline else'candidate-result.json')).write_text(json.dumps(out,indent=2),'utf8');sys.exit(not result.wasSuccessful())
