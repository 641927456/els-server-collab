"""Compare cached publication with the original native manifest predicates."""
import ast,contextlib,importlib.util,json,sys,types,unittest,uuid
from pathlib import Path
from unittest.mock import patch
H=Path(__file__).resolve().parent;A=H.parent
from hypothesis import given,settings,strategies as st
B=A/'runtime-parent'
S=A/'source/els_server'

def module(name,**fields):
 m=types.ModuleType(name);m.__dict__.update(fields);return m
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
class Event:
 def __init__(self,event_id,kind):self.event_id=event_id;self.kind=kind
deps={name:module(name,__path__=[])for name in('els_server','els_server.domain','els_server.protocol')}
deps.update({'els_server.domain.dungeon_time_sync':module('clock',context=lambda s:(s.shop_session_id,s.account.uid,s.reward_run_id,s.part)if s.synced else None),
 'els_server.protocol.protocol_codec':module('codec',Event=Event),
 'els_server.domain.equipment_chip_flow':module('lease',current_lease=lambda s:s.lease),
 'els_server.domain.session_auxiliary':module('aux',friends_auxiliary_session=lambda s:True),
 'els_server.domain.photo_zone_flow':module('photo',manifest=lambda *a:None,relay_target=lambda *a:None)})
with patch.dict(sys.modules,deps):
 old=load('original_solo_realtime',B/'els_server/realtime.py');new=load('candidate_solo_realtime',S/'realtime.py')
tree=ast.parse((B/'els_server/domain/friends_dungeon.py').read_bytes())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='FriendsDungeons')
namespace=dict(uuid=uuid,SessionOrderError=ValueError)
nodes=[n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name in('manifest','relay_target','_current_transport_member','_current_transport_roster')]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-native-manifest','exec'),namespace)
class Provider:
 def __init__(self):self.rooms={}
 def room(self,s):return self.rooms.get(s)
 def manifest(self,*args):return None
 def relay_target(self,*args):return None
class Registry:
 def __init__(self):self.active=True;self.reads=0
 @contextlib.contextmanager
 def enabled_snapshot(self):self.reads+=1;yield
 def enabled(self,account):return self.active
class Dungeons(Provider):
 def __init__(self,world):super().__init__();self.world=world;self.calls=0;self.fail=False
 def transport_room(self,s):return self.room(s)or self.world.field_bosses.room(s)
 def manifest(self,app,account):
  self.calls+=1
  if self.fail:raise ValueError('Manifest failed')
  return namespace['manifest'](self,app,account)
 def relay_target(self,*args):return namespace['relay_target'](self,*args)
 _current_transport_member=namespace['_current_transport_member']
 _current_transport_roster=namespace['_current_transport_roster']
class Actor:pass
def fixture():
 w=types.SimpleNamespace(party_of={})
 for name in('pvp','field_bosses','weddings','racing','pet_battles'):setattr(w,name,Provider())
 w.dungeons=Dungeons(w)
 s=Actor();s.identity={'id':1};s.account=types.SimpleNamespace(uid=1001,account_id=1);s.shop_session_id=str(uuid.uuid4())
 s.phase='dungeon_active';s.role='game';s.released=False;s.coop_error=None;s.social_overflow=False;s.client_build='dx11_260923'
 s.enter_dungeon=True;s.dungeon_return_pending=False;s.reward_run_id=str(uuid.uuid4());s.dungeon_participants=frozenset((1001,));s.photo_zone=None
 s.synced=True;s.part=0;s.lease=True
 a=types.SimpleNamespace(world=w,config=types.SimpleNamespace(mode='friends'),registry=Registry(),playing={1:s})
 s.application=a;return a,s
def view(v):return tuple(dict(getattr(v,n))for n in('manifests','routes','clocks','required','bindings','auxiliary'))+(v.legacy,)
def publish(state,app,**kwargs):
 def handle():pass
 with patch.dict(sys.modules,deps):state.publish(app,handle,(Event(0x202,0x9e),),**kwargs)

class SoloRoutingTests(unittest.TestCase):
 def test_unchanged_native_solo_reuses_bytes_but_refreshes_registry(self):
  app,s=fixture();state=new.RealtimeState();publish(state,app);first=view(state.view)
  for _ in range(20):publish(state,app)
  self.assertEqual(view(state.view),first);self.assertEqual(app.world.dungeons.calls,1);self.assertEqual(app.registry.reads,21)
  self.assertEqual(state.published,1);self.assertEqual(state.reused,20)
  app.registry.active=False;publish(state,app);self.assertFalse(state.view.manifests);self.assertFalse(state.solo_manifests)
  app.registry.active=True;publish(state,app);self.assertEqual(app.world.dungeons.calls,2)
 @settings(max_examples=100,deadline=None,database=None)
 @given(st.lists(st.sampled_from(('uid','owner','identity','token','phase','role','released','coop','entered','returning','reward','participants','party','synced','part','lease','enabled','town','restore')),min_size=1,max_size=60))
 def test_each_publication_matches_original_after_actor_scene_and_authority_changes(self,actions):
  app,s=fixture();expected=old.RealtimeState();actual=new.RealtimeState();publish(expected,app);publish(actual,app)
  for action in actions:
   if action=='uid':s.account.uid=1002 if s.account.uid==1001 else 1001
   elif action=='owner':s.account.account_id=2 if s.account.account_id==1 else 1
   elif action=='identity':s.identity['id']=2 if s.identity['id']==1 else 1
   elif action=='token':s.shop_session_id=str(uuid.uuid4())
   elif action=='phase':s.phase='dungeon_loading'if s.phase=='dungeon_active'else'dungeon_active'
   elif action=='role':s.role='frontend'if s.role=='game'else'game'
   elif action=='released':s.released=not s.released
   elif action=='coop':s.coop_error=None if s.coop_error else'closed'
   elif action=='entered':s.enter_dungeon=not s.enter_dungeon
   elif action=='returning':s.dungeon_return_pending=not s.dungeon_return_pending
   elif action=='reward':s.reward_run_id=str(uuid.uuid4())if s.reward_run_id is None else None
   elif action=='participants':s.dungeon_participants=frozenset((s.account.uid,))if s.dungeon_participants is None else None
   elif action=='party':app.world.party_of.pop(s,None)if s in app.world.party_of else app.world.party_of.update({s:{'members':[s]}})
   elif action=='synced':s.synced=not s.synced
   elif action=='part':s.part+=1
   elif action=='lease':s.lease=not s.lease
   elif action=='enabled':app.registry.active=not app.registry.active
   elif action=='town':s.phase='town_ready'
   elif action=='restore':s.phase='dungeon_active';s.role='game';s.released=False;s.coop_error=None;s.enter_dungeon=True;s.dungeon_return_pending=False;s.reward_run_id=str(uuid.uuid4());s.dungeon_participants=frozenset((s.account.uid,));s.identity['id']=s.account.account_id=1;app.world.party_of.clear()
   publish(expected,app);publish(actual,app);self.assertEqual(view(actual.view),view(expected.view),action)
 def test_excluded_actor_retains_original_view_then_revalidates_when_available(self):
  app,s=fixture();state=new.RealtimeState();publish(state,app);before=view(state.view)
  s.reward_run_id=str(uuid.uuid4());publish(state,app,exclude=frozenset((1,)));self.assertEqual(view(state.view),before)
  publish(state,app);self.assertNotEqual(view(state.view),before);self.assertEqual(app.world.dungeons.calls,2)
 def test_failure_clears_cached_manifests_with_original_fail_closed_view(self):
  app,s=fixture();state=new.RealtimeState();publish(state,app);s.shop_session_id=str(uuid.uuid4());app.world.dungeons.fail=True
  with self.assertRaisesRegex(ValueError,'Manifest failed'):publish(state,app)
  self.assertFalse(state.view.manifests);self.assertFalse(state.solo_manifests)
 def test_pet_room_and_photo_lobby_do_not_reuse_ordinary_solo_payload(self):
  for special in ('pet','photo'):
   with self.subTest(special=special):
    app,s=fixture();state=new.RealtimeState();publish(state,app)
    if special=='pet':app.world.pet_battles.rooms[s]=object()
    else:s.photo_zone={'room':None}
    publish(state,app);publish(state,app)
    self.assertEqual(app.world.dungeons.calls,3);self.assertFalse(state.solo_manifests)
if __name__=='__main__':unittest.main()
