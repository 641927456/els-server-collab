import ast,importlib.util,json,sys,time,types,unittest
from pathlib import Path
from unittest.mock import patch
H=Path(__file__).resolve().parent;A=H.parent;S=A/'source/els_server'
from hypothesis import given,settings,strategies as st
base=A/'runtime-parent'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
codec=load('original_display_codec',base/'els_server/protocol/protocol_codec.py');Event=codec.Event
m=load('display_auxiliary',S/'domain/session_auxiliary.py');m.time=types.SimpleNamespace(monotonic=lambda:100.)
class LocalSession:
 def handle(self,event):
  self.level=self.result_level;self.effect();return self.replies
 def periodic_notifications(self):return self.replies
class FriendsSession(LocalSession):pass
class Clock:
 def __init__(self):self.seen=[]
 def observe(self,s):self.seen.append(s.level)
class Flow:
 def __init__(self):self.online=Clock();self.calls=0
 def after_reply(self,s,replies):self.calls+=1;return replies
application=types.ModuleType('els_server.application');application.FriendsSession=FriendsSession
local=types.ModuleType('els_server.domain.local_session');local.LocalSession=LocalSession
modules={name:types.ModuleType(name)for name in('els_server','els_server.domain','els_server.protocol')}
for module in modules.values():module.__path__=[]
modules.update({'els_server.application':application,'els_server.domain.local_session':local,'els_server.protocol.protocol_codec':codec,'els_server.domain.session_auxiliary':m})
tree=ast.parse((S/'application.py').read_bytes());node=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='invoke_with_reads')
worker=compile(ast.Module(body=[node],type_ignores=[]),'actual-display-worker','exec')
def session(phase='dungeon_active'):
 s=FriendsSession();s.client_build='dx11_260923';s.role='game';s.phase=phase;s.released=False;s.social_overflow=False;s.coop_error=None
 s.dungeon_substage_synced=True;s.reward_run_id='owned-run';s.part_end_notified=True;s.gate_stage_loading=False;s.clear_notified=False;s.dungeon_failed=False
 s.next_periodic=101.;s._periodic_pending=False;s.level=s.result_level=1;s.activity2026_awards=Flow();s.replies=[];s.effect=lambda:None
 s.account=types.SimpleNamespace(uid=1001,store=types.SimpleNamespace(uid=1001),character_identity=lambda:dict(level=s.level))
 s.identity={'id':1};s.application=types.SimpleNamespace(playing={1:s});return s
def invoke(s,event=None):
 function=s.periodic_notifications if event is None else s.handle
 scope=dict(function=function,args=()if event is None else(event,),kwargs={},sample={},LocalSession=LocalSession,FriendsSession=FriendsSession,time=time)
 exec(worker,scope)
 with patch.dict(sys.modules,modules):return scope['invoke_with_reads']()
class DisplayMaintenanceTests(unittest.TestCase):
 def test_terminal_ack_keeps_original_result_without_own_activity_reads(self):
  for code in (0,2005):
   with self.subTest(code=code):
    s=session();s.replies=[Event(0x201,kind=0x9f,payload=code.to_bytes(4,'big'))]
    self.assertIs(invoke(s,Event(0x202,kind=0x9e)),s.replies)
    self.assertEqual(s.activity2026_awards.online.seen,[]);self.assertEqual(s.activity2026_awards.calls,0)
    self.assertEqual(int.from_bytes(s.replies[0].payload,'big'),code)
 def test_terminal_reply_with_owned_state_observes_after_adoption(self):
  for kind in (0xaf,0xc1,0x2b,0x106):
   with self.subTest(kind=kind):
    s=session();s.result_level=2;s.replies=[Event(0x201,kind=0x9f),Event(0x201,kind=kind)]
    self.assertIs(invoke(s,Event(0x202,kind=0x9e)),s.replies)
    self.assertEqual(s.activity2026_awards.online.seen,[2]);self.assertEqual(s.activity2026_awards.calls,1)
 def test_town_move_peer_only_reply_keeps_original_save_handler(self):
  s=session('town_ready');s.replies=[Event(0x201,kind=k)for k in(0x22a,0x22e,0x18e)]
  self.assertIs(invoke(s,Event(0x202,kind=0x22b)),s.replies);self.assertEqual(s.activity2026_awards.online.seen,[]);self.assertEqual(s.activity2026_awards.calls,0)
  s.replies.append(Event(0x201,kind=0x2b));self.assertIs(invoke(s,Event(0x202,kind=0x22b)),s.replies);self.assertEqual(s.activity2026_awards.calls,1)
 def test_due_periodic_clock_remains_complete_but_quiet_peer_delivery_skips_it(self):
  for due,observations,calls in ((False,[],0),(True,[1,1],1)):
   s=session('town_ready');s.next_periodic=100. if due else 101.;s.replies=[Event(0x201,kind=0x22a)]
   self.assertIs(invoke(s),s.replies);self.assertEqual(s.activity2026_awards.online.seen,observations);self.assertEqual(s.activity2026_awards.calls,calls)
 def test_completed_capped_part_does_not_observe_the_following_gate(self):
  s=session();s.level=s.result_level=99;s.dungeon_run=types.SimpleNamespace(next={'kind':0})
  s.replies=[Event(0x201,kind=0xbc),Event(0x201,kind=0xbd)]
  s.effect=lambda:setattr(s.dungeon_run,'next',{'kind':1})
  self.assertIs(invoke(s,Event(0x202,kind=0xbb)),s.replies)
  self.assertEqual(s.activity2026_awards.online.seen,[]);self.assertEqual(s.activity2026_awards.calls,1)
 def test_completed_part_still_observes_level_scene_and_clear_changes(self):
  for change in ('level','scene','clear','failure'):
   with self.subTest(change=change):
    s=session();s.level=s.result_level=99;s.dungeon_run=types.SimpleNamespace(next={'kind':0});s.replies=[Event(0x201,kind=0xbc)]
    if change=='level':s.result_level=98
    else:s.effect=lambda:setattr(s,{'scene':'dungeon_substage_synced','clear':'clear_notified','failure':'dungeon_failed'}[change],change!='scene')
    invoke(s,Event(0x202,kind=0xbb));self.assertEqual(s.activity2026_awards.online.seen,[s.result_level]);self.assertEqual(s.activity2026_awards.calls,1)
 @settings(max_examples=150,deadline=None,database=None)
 @given(st.sampled_from(('game','frontend')),st.sampled_from(('dx11_260923','legacy')),st.sampled_from(('dungeon_active','town_ready','pvp_active')),st.booleans(),st.booleans(),st.sampled_from((0x201,0x202)))
 def test_terminal_fast_path_retains_original_role_scene_and_run_boundaries(self,role,build,phase,synced,run,event_id):
  s=session(phase);s.role=role;s.client_build=build;s.dungeon_substage_synced=synced;s.reward_run_id='run'if run else None
  with patch.dict(sys.modules,modules):actual=m.maintenance_request(s,Event(event_id,kind=0x9e))
  self.assertEqual(bool(actual),role=='game'and build=='dx11_260923'and phase=='dungeon_active'and synced and run and event_id==0x202)
if __name__=='__main__':unittest.main()
