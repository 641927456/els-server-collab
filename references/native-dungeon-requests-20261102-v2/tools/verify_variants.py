"""Same-root protocol regressions across every current portal and trigger rule."""
import copy,json,struct,unittest,sys,uuid,ast
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import verify as base
from els_server.domain import dungeon_flow as flow,native_line_triggers as triggers
from els_server.domain.friends_spawns import capture_static_origin
from els_server.protocol.protocol_codec import Event,decode_event
audit=json.loads((HERE/'audit.json').read_bytes());native=json.loads((HERE/'native-envelopes.json').read_bytes())

def event(kind,payload):
 e=next(r for r in native['rows']if r['kind']==kind)
 original=decode_event(bytes.fromhex(e['plaintext_hex']))
 return Event(original.event_id,original.performers,original.uid,original.target_uid,kind,payload,original.payload_mode)

def trigger_fixture(row,group=False):
 if group:dispatcher,room,members=base.group_fixture(row['stage'],row['part'],row['dungeon'])
 else:
  s,t=base.fixture(row['stage'],row['part'],row['dungeon']);members=(s,)
 for m in members:
  run=m.dungeon_run;run.defeated={};m.defeated_npcs=run.defeated
  npc=row.get('npc_template')
  if npc is not None and not any(n['template']==npc for n in run.current['npcs']):
   # Select the declared alternative roster, never create an absent source actor.
   from els_server.domain.dungeon_routes import SOURCE_NPC_GROUP_WEIGHTS
   groups=run.graph['stages'][str(run.stage)]['parts'][str(run.part)]['groups']
   def contains(g):return any(n.get('template')==npc or any(o['template']==npc for o in n.get('options',()))for n in g['npcs'])
   target=next(g for g in groups if contains(g));old=run.draw
   def draw(label,total,old=old,target=target,groups=groups,run=run):
    if label==f'group:{run.stage}:{run.part}' and target['index']!=-1:
     weights=SOURCE_NPC_GROUP_WEIGHTS[run.graph['source_sha256'],run.stage,run.part]
     index=next(i for i,g in enumerate(groups[1:])if g['index']==target['index']);return sum(weights[:index])
    if label.startswith(f'presence:{run.stage}:{run.part}:'):return 0
    return old(label,total)
   run.draw=draw;run._load_stage(row['stage']);run.part=row['part'];run.loaded()
  if npc is not None:assert any(n['template']==npc for n in run.current['npcs']),row
 if group:capture_static_origin(room);return dispatcher,room,members
 return members[0]

def group_request(dispatcher,room,s,e):
 out=dispatcher.request(s,e)
 return flow.handle(s,e)if out is None else out

def trigger_state(s):
 run=s.dungeon_run
 return (base.state(s),set(getattr(run,'native_line_triggers',())),[(n['key'],n['hp'],n['active'])for n in run.current['npcs']])

class Variants(unittest.TestCase):
 def test_early_curtain_native_request_requires_no_kills(self):
  s,t=base.fixture(0,0);before=base.state(s)
  out=flow.handle(s,event(0xb8,b'\0'))
  expected=-1 if base.args.baseline else 0
  self.assertEqual(struct.unpack('>i',out[0].payload)[0],expected);self.assertEqual(base.state(s),before)
  self.assertFalse(s.dungeon_run.portal_requested)

 def test_all_25_portals_keep_contact_kills_delay_and_target(self):
  for row in audit['portals']:
   with self.subTest(source=(row['dungeon'],row['stage'],row['part'])):
    s,t=base.fixture(row['stage'],row['part'],row['dungeon']);base.cleared(s);run=s.dungeon_run
    # Inactive required controllers are not silently turned into combat kills.
    self.assertEqual(flow.periodic(s),[]);e=base.report(s)
    out=flow.handle(s,e)
    if base.args.baseline:self.assertIsNone(out);continue
    self.assertEqual([v.kind for v in out],[0x472]+([0xba]if row['delay']==0 else []))
    self.assertTrue(run.portal_requested);target=dict(run.next)
    if row['delay']:
     t[0]=row['delay']-.001;self.assertEqual(flow.periodic(s),[])
     t[0]=row['delay'];self.assertEqual([v.kind for v in flow.periodic(s)],[0xba])
    out=flow.handle(s,Event(0x202,kind=0xbb,payload=struct.pack('>b',run.part)))
    self.assertIn(0xb2,[v.kind for v in out]);self.assertEqual((run.stage,run.part),(target['stage'],target['part']))

 def test_group_trigger_no_longer_rejected_by_solo_roster_guard(self):
  row=audit['group_trigger_rules'][0];dispatcher,room,members=trigger_fixture(row,True);s=members[0]
  before=[trigger_state(m)for m in members];e=event(0x30a,struct.pack('>i',row['trigger']))
  out=group_request(dispatcher,room,s,e)
  if base.args.baseline:
   self.assertEqual([(v.kind,v.payload)for v in out],[(0x30b,struct.pack('>i',-1))]);self.assertEqual([trigger_state(m)for m in members],before)
  else:
   self.assertEqual([v.kind for v in out],[0x30b,0x30c]);self.assertEqual([v.kind for v in members[1].mailbox.drain()],[0x30c])

 def test_all_103_group_rules_from_master_and_member(self):
  for row in audit['group_trigger_rules']:
   with self.subTest(source=(row['dungeon'],row['stage'],row['part'],row['trigger'])):
    dispatcher,room,members=trigger_fixture(row,True);master,member=members;e=event(0x30a,struct.pack('>i',row['trigger']))
    before=[base.state(m)for m in members]
    self.assertEqual([v.kind for v in group_request(dispatcher,room,member,e)],[0x30b,0x30c])
    self.assertEqual([v.kind for v in master.mailbox.drain()],[0x30c])
    again=group_request(dispatcher,room,master,e)
    self.assertEqual([v.kind for v in again],[0x30b,0x30c]if row['native_loop']else[0x30b])
    self.assertEqual([v.kind for v in member.mailbox.drain()],[0x30c]if row['native_loop']else[])
    self.assertEqual([base.state(m)for m in members],before)
    self.assertEqual(master.dungeon_run.native_line_triggers,member.dungeon_run.native_line_triggers)

 def test_all_126_solo_rules_preserve_loop_and_duplicate_semantics(self):
  for row in [*audit['group_trigger_rules'],*audit['solo_trigger_rules']]:
   with self.subTest(source=(row['dungeon'],row['stage'],row['part'],row['trigger'])):
    s=trigger_fixture(row);before=base.state(s);e=event(0x30a,struct.pack('>i',row['trigger']))
    self.assertEqual([v.kind for v in triggers.handle(s,e)],[0x30b,0x30c])
    self.assertEqual([v.kind for v in triggers.handle(s,e)],[0x30b,0x30c]if row['native_loop']else[0x30b])
    self.assertEqual(base.state(s),before)

 def test_late_curtain_native_envelope_is_accepted_outside_old_three_maps(self):
  dispatcher,room,members=base.group_fixture();room.phase='substage';room.previous_part=1
  for m in members:
   m.client_build='dx11_260923';m.gate_stage_loading=True;m.dungeon_substage_synced=False
   m.dungeon_return_pending=False;m.dungeon_end_payload=None;m.reward_receipt=None
   m.dungeon_run.completed_transition=dict(target=(1,2,m.dungeon_run.visits),parts=(b'\1',b'\2'))
  before=[trigger_state(m)for m in members]
  for m in members:
   out=dispatcher.portal(room,m,event(0xb8,b'\2'))
   self.assertEqual(out,[] if base.args.baseline else [Event(0x201,kind=0xb9,payload=bytes(4))])
  self.assertEqual([trigger_state(m)for m in members],before)

 def test_curtain_wait_is_acknowledged_before_shared_BB_barrier(self):
  dispatcher,room,members=base.group_fixture();room.phase='part_end'
  for m in members:m.part_end_notified=True
  before=[trigger_state(m)for m in members]
  for m in members:
   out=dispatcher.portal(room,m,event(0xb8,b'\2'))
   self.assertEqual(out,[] if base.args.baseline else [Event(0x201,kind=0xb9,payload=bytes(4))])
  self.assertEqual([trigger_state(m)for m in members],before);self.assertEqual(room.phase,'part_end')

 def test_shared_trigger_generation_lease_room_and_mailbox_rejections(self):
  row=audit['group_trigger_rules'][0]
  from els_server.domain.local_session import SessionOrderError
  for change in ('generation','lease','phase','failed','id','payload','uid','performer','mailbox','encode','state_divergence'):
   with self.subTest(change=change):
    dispatcher,room,members=trigger_fixture(row,True);s,peer=members;e=event(0x30a,struct.pack('>i',row['trigger']))
    if change=='generation':peer.dungeon_run.visits+=1
    if change=='lease':s.application.playing[s.account.account_id]=object()
    if change=='phase':room.phase='substage'
    if change=='failed':peer.dungeon_failed=True
    if change=='id':e=event(0x30a,struct.pack('>i',999999))
    if change=='payload':e=event(0x30a,b'')
    if change=='uid':e=Event(0x202,performers=(0,),uid=1,kind=0x30a,payload=e.payload)
    if change=='performer':e=Event(0x202,performers=(2,),kind=0x30a,payload=e.payload)
    if change=='state_divergence':peer.dungeon_run.native_line_triggers={(1,1,1,1)}
    if change=='mailbox':
     for _ in range(256):peer.mailbox.append(Event(0x201,kind=1,payload=b'x'))
    before=[trigger_state(m)for m in members];queued=tuple(peer.mailbox.messages)
    if change=='mailbox':
     with self.assertRaises(SessionOrderError):group_request(dispatcher,room,s,e)
    elif change=='encode':
     with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('controlled native trigger encode')):
      with self.assertRaises(RuntimeError):group_request(dispatcher,room,s,e)
    else:self.assertEqual(group_request(dispatcher,room,s,e)[0].payload,struct.pack('>i',-1))
    self.assertEqual([trigger_state(m)for m in members],before);self.assertEqual(tuple(peer.mailbox.messages),queued)

 def test_solo_trigger_encoding_failure_does_not_poison_duplicate_state(self):
  s=trigger_fixture(audit['group_trigger_rules'][0]);before=trigger_state(s)
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('encode')):
   with self.assertRaises(RuntimeError):triggers.handle(s,event(0x30a,bytes(4)))
  self.assertEqual(trigger_state(s),before)
  self.assertEqual([e.kind for e in triggers.handle(s,event(0x30a,bytes(4)))],[0x30b,0x30c])

 def test_curtain_rejects_foreign_envelope_and_lease(self):
  for change in ('uid','performer','mode','lease','part'):
   s,t=base.fixture(0,0);e=event(0xb8,b'\0')
   kw=dict(event_id=e.event_id,performers=e.performers,uid=e.uid,target_uid=e.target_uid,kind=e.kind,payload=e.payload,payload_mode=e.payload_mode)
   if change=='uid':kw['uid']=1001
   if change=='performer':kw['performers']=(1,)
   if change=='mode':kw['payload_mode']=1
   if change=='lease':s.application.playing[71]=object()
   if change=='part':kw['payload']=b'\x7f'
   before=base.state(s);self.assertEqual(flow.handle(s,Event(**kw))[0].payload,struct.pack('>i',-1));self.assertEqual(base.state(s),before)

 def test_source_guard_detects_old_b8_contact_conflation(self):
  p=HERE/'candidate/els_server/domain/dungeon_flow.py';tree=ast.parse(p.read_text('utf8'));checked=0
  for node in ast.walk(tree):
   if not isinstance(node,ast.If)or 'event.kind == 184'!=ast.unparse(node.test):continue
   branch=ast.Module(body=node.body,type_ignores=[]);text=ast.unparse(branch);checked+=1
   self.assertNotIn('portal_requested = True',text);self.assertNotIn('run.defeated',text)
  self.assertEqual(checked,1)

if __name__=='__main__':
 names=['test_early_curtain_native_request_requires_no_kills','test_group_trigger_no_longer_rejected_by_solo_roster_guard','test_late_curtain_native_envelope_is_accepted_outside_old_three_maps']
 suite=unittest.TestSuite(Variants(n)for n in names)if base.args.baseline else unittest.defaultTestLoader.loadTestsFromTestCase(Variants)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 out=dict(ok=result.wasSuccessful(),baseline=base.args.baseline,tests=result.testsRun,skipped=len(result.skipped),portal_segments=25,group_trigger_rules=103,solo_trigger_rules=126,
  failures=[str(t)+'\n'+why for t,why in result.failures+result.errors],natural_GUI=False,natural_battle=False)
 (HERE/('variants-baseline.json'if base.args.baseline else'variants-result.json')).write_text(json.dumps(out,indent=2),'utf8');sys.exit(not result.wasSuccessful())
