"""Control-flow models exercise original worker code with classified dependencies.

These are scheduling/clock contracts, not substitutes for native gameplay QA.
"""
import ast,collections,contextlib,contextvars,threading,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import sys
H=Path(__file__).resolve().parent;S=H.parent/'source/els_server'
def node(path,owner,name):
 tree=ast.parse(path.read_bytes());c=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==owner)
 return next(n for n in c.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name==name)
def module(name,**fields):
 m=types.ModuleType(name);m.__dict__.update(fields);return m

class ActorBase:pass
class Actor(ActorBase):
 def __init__(self):self.calls=0;self.result=[types.SimpleNamespace(event_id=0x201,kind=0xc1)];self.activity2026_awards=None;self.phase='dungeon_active';self.effect=lambda:None
 def handle(self,*args):self.calls+=1;self.effect();return self.result
 def periodic_notifications(self):self.calls+=1;self.effect();return self.result

class WorkerModels(unittest.TestCase):
 def invoke(self,s,name='handle',flags=(False,),queue=None,publish_error=False,context=None,ordinary_move=False):
  wake_context=context if context is not None else contextvars.ContextVar('model-town-wake',default=None)
  namespace=dict(time=time,LocalSession=ActorBase,FriendsSession=Actor,_town_move_wakes=wake_context)
  n=node(S/'application.py','Application','_worker_call');exec(compile(ast.Module(body=[n],type_ignores=[]),'actual-worker-control','exec'),namespace)
  observations=[];predicates=iter(flags or());self.trace=[];self.after=[]
  def observe(actor):observations.append(actor)
  def after(actor,reply):self.after.append(reply);return reply
  if flags is not None:s.activity2026_awards=types.SimpleNamespace(online=types.SimpleNamespace(observe=observe),after_reply=after)
  @contextlib.contextmanager
  def scope(*unused):
   try:yield
   finally:self.trace.append('scope-exit')
  def publish(*a,**kw):
   self.trace.append('publish');self.published=kw
   if publish_error:raise RuntimeError('publication failure')
  workers=types.SimpleNamespace(worker_scope=scope,candidate=lambda *a:True,publish=publish,ordinary_town_move=lambda *a:ordinary_move)
  app=types.SimpleNamespace(dungeon_workers=workers,read_connections=None,performance=types.SimpleNamespace(record=lambda *a,**k:None))
  deps={
   'els_server.performance':module('perf',captured_calls=lambda:None,worker_timing=lambda s:contextlib.nullcontext(),request_category=lambda *a:'model'),
   'els_server.storage.read_scope':module('reads',committed_reads=lambda **kw:contextlib.nullcontext()),
   'els_server.domain.native_session_sources':module('sources',capture=lambda fn,args,kw,invoke:invoke()),
   'els_server.domain.dungeon_result_stats':module('stats',finalize=lambda s,r:r),
   'els_server.periodic_work':module('periodics',next_poll_deadline=lambda *a:0),
   'els_server.domain.session_auxiliary':module('aux',auxiliary_call=lambda *a:False,activity_due=lambda *a,**kw:next(predicates),maintenance_reply=lambda *a:False,town_peer_reply=lambda *a:False)}
  for package in ['els_server','els_server.storage','els_server.domain']:
   deps[package]=module(package,__path__=[])
  function=getattr(s,name);args=()if name=='periodic_notifications'else(types.SimpleNamespace(kind=0xad),)
  with patch.dict(sys.modules,deps):result=namespace['_worker_call'](app,function,args,{},time.perf_counter(),queue_timing=queue)
  return result,observations
 def test_still_capped_handle_keeps_reply_without_duplicate_clock(self):
  s=Actor();result,clocks=self.invoke(s,flags=(False,False));self.assertIs(result,s.result);self.assertEqual(s.calls,1);self.assertEqual(clocks,[]);self.assertEqual(self.after,[s.result])
 def test_final_state_change_observes_even_when_initial_state_skipped(self):
  s=Actor();_,clocks=self.invoke(s,flags=(False,True));self.assertEqual(clocks,[s]);self.assertEqual(self.after,[s.result])
 def test_resumed_periodic_slice_still_refreshes_clock(self):
  s=Actor();_,clocks=self.invoke(s,name='periodic_notifications',flags=(False,));self.assertEqual(clocks,[s]);self.assertEqual(self.after,[s.result])
 def test_observed_and_failed_handler_keep_original_clock_and_error(self):
  s=Actor();_,clocks=self.invoke(s,flags=(True,));self.assertEqual(clocks,[s,s])
  s=Actor();s.effect=lambda:(_ for _ in()).throw(ValueError('economic failure'))
  with self.assertRaisesRegex(ValueError,'economic failure'):self.invoke(s,flags=(True,))
  self.assertFalse(self.after);self.assertTrue(self.published['failed'])
 def wake_case(self,fail):
  context=contextvars.ContextVar('model-town-wake',default=None);outer=object();token=context.set(outer);s=Actor();called=[];scheduled=[]
  class Loop:
   def call_soon_threadsafe(loop,callback,*args):
    self.assertIs(context.get(),outer);self.assertEqual(self.trace[-2:],['scope-exit','publish']);scheduled.append((callback,args))
  class Event:
   def __init__(event,label):event.label=label
   def set(event):
    self.assertIs(context.get(),outer);called.append(event.label)
  loop=Loop();events=(Event('one'),Event('two'))
  def produce():
   batch=context.get();self.assertIsInstance(batch,dict)
   for event in (*events,events[0]):batch.setdefault(loop,set()).add(event)
   self.assertFalse(called);self.assertFalse(scheduled)
  s.effect=produce
  try:
   if fail:
    with self.assertRaisesRegex(RuntimeError,'publication failure'):self.invoke(s,flags=None,queue=dict(town_movement=True),publish_error=True,context=context)
   else:self.invoke(s,flags=None,queue=dict(town_movement=True),context=context)
   self.assertEqual(len(scheduled),1);self.assertFalse(called)
   for callback,args in scheduled:callback(*args)
   self.assertCountEqual(called,['one','two']);self.assertIs(context.get(),outer)
  finally:context.reset(token)
 def test_wake_is_after_scope_and_publication(self):self.wake_case(False)
 def test_publication_failure_still_retires_wakes_and_context(self):self.wake_case(True)
 def test_peer_window_closes_on_normal_and_failed_worker_exit(self):
  for name in('handle','periodic_notifications'):
   for fail in(False,True):
    s=Actor();s.phase='town_ready'
    def effect():
     self.assertTrue(s._peer_drain_open)
     if fail:raise ValueError('Owned peer-window failure')
    s.effect=effect
    if fail:
     with self.assertRaisesRegex(ValueError,'Owned peer-window failure'):self.invoke(s,name=name,flags=None,ordinary_move=name=='handle')
    else:self.invoke(s,name=name,flags=None,ordinary_move=name=='handle')
    self.assertFalse(s._peer_drain_open)

class PeerReadModels(unittest.TestCase):
 def test_captured_mailbox_closes_bypass_before_any_messages_are_removed(self):
  n=node(S/'application.py','FriendsSession','_mailbox_messages');namespace={};exec(compile(ast.Module(body=[n],type_ignores=[]),'actual-mailbox-capture','exec'),namespace)
  actor=types.SimpleNamespace(_peer_drain_open=True,activity2026_awards=None);messages=[]
  def drain():self.assertFalse(actor._peer_drain_open);return messages
  actor.mailbox=types.SimpleNamespace(drain=drain)
  deps={name:module(name,__path__=[])for name in('els_server','els_server.domain')}
  deps.update({'els_server.domain.quest_flow':module('quests',shared_updates=lambda *a:[]),
   'els_server.domain.growth_guide_flow':module('guide',synchronize=lambda s,r:r),
   'els_server.domain.achievement_flow':module('achievement',synchronize=lambda s,e,r:r)})
  with patch.dict(sys.modules,deps):self.assertEqual(namespace['_mailbox_messages'](actor),messages)
 def test_solo_no_room_omits_unused_identity_but_shared_and_admission_keep_it(self):
  n=node(S/'application.py','FriendsSession','_dungeon_request');namespace={};exec(compile(ast.Module(body=[n],type_ignores=[]),'actual-shared-dispatch','exec'),namespace)
  t=ast.parse((S/'dungeon_workers.py').read_bytes());assignment=next(n for n in t.body if isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='KINDS'for v in n.targets));kinds=frozenset(ast.literal_eval(assignment.value.args[0]))
  for room,kind,expected in((None,0xad,[]),(object(),0xad,['identity','request']),(None,0x7d4,['identity','request'])):
   calls=[];actor=types.SimpleNamespace(phase='dungeon_active',active_map=20000,_mailbox_messages=lambda:[])
   def identity(*a):calls.append('identity')
   def request(*a):calls.append('request');return []
   actor.application=types.SimpleNamespace(world=types.SimpleNamespace(dungeons=types.SimpleNamespace(room=lambda *a:room,request=request)))
   deps={name:module(name,__path__=[])for name in('els_server','els_server.domain')}
   deps.update({'els_server.dungeon_workers':module('workers',KINDS=kinds),
    'els_server.domain.elixir_flow':module('elixir',remember=lambda s,r:r),
    'els_server.domain.dungeon_requests':module('dungeons',accepts=lambda *a:True,identity_before=identity,activity_changed=lambda *a:False),
    'els_server.domain.tenebros_storage_flow':module('shadow',abandon=lambda *a:None),
    'els_server.domain.growth_guide_flow':module('guide',synchronize=lambda s,r:r)})
   with patch.dict(sys.modules,deps):answer=namespace['_dungeon_request'](actor,types.SimpleNamespace(kind=kind),1)
   self.assertEqual(calls,expected);self.assertEqual(answer,[]if expected else None)

class MailboxModels(unittest.TestCase):
 def mailbox(self,notify):
  tree=ast.parse((S/'domain/friends_world.py').read_bytes());c=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Mailbox');namespace=dict(deque=collections.deque,RLock=threading.RLock,SessionOrderError=RuntimeError)
  exec(compile(ast.Module(body=[c],type_ignores=[]),'actual-mailbox','exec'),namespace);return namespace['Mailbox'](notify)
 def test_first_move_wakes_even_behind_member_notice(self):
  calls=[];box=self.mailbox(calls.append);notice=types.SimpleNamespace(payload=b'notice');a=types.SimpleNamespace(payload=b'a');b=types.SimpleNamespace(payload=b'b')
  box.append(notice);box.append(a,1001);box.append(b,1001);self.assertEqual(calls,[False,True]);self.assertEqual(box.drain(),[notice,b])
  box.append(a,1001);self.assertEqual(calls,[False,True,True])
 def test_rejected_move_does_not_wake_or_modify_full_mailbox(self):
  calls=[];box=self.mailbox(calls.append);notice=types.SimpleNamespace(payload=b'n')
  for _ in range(256):box.append(notice)
  with self.assertRaises(RuntimeError):box.append(types.SimpleNamespace(payload=b'm'),1001)
  self.assertEqual(calls,[False]);self.assertEqual(box.bytes,256);self.assertEqual(box.moves,{})

class PublicationModels(unittest.TestCase):
 def check_case(self,kind,unchanged,expected):
  namespace={};n=node(S/'dungeon_workers.py','DungeonWorkers','publish');exec(compile(ast.Module(body=[n],type_ignores=[]),'actual-publication','exec'),namespace)
  s=Actor();s.identity=dict(id=1);domain=types.SimpleNamespace(lock=threading.RLock(),members=(s,));calls=[]
  app=types.SimpleNamespace(read_connections=None,world_lock=threading.RLock(),world=types.SimpleNamespace(party_of={}),realtime=types.SimpleNamespace(unchanged_scope=lambda *a:unchanged,publish=lambda *a,**k:calls.append(True)))
  workers=types.SimpleNamespace(application=app,session_for=lambda *a:s,_domain_for=lambda s:(1,domain),candidate=lambda *a:True,catalog_lock=threading.RLock(),domains={1:domain},foreground_publish_skips=0)
  deps={'els_server':module('els_server',__path__=[]),'els_server.domain':module('els_server.domain',__path__=[]),'els_server.domain.session_auxiliary':module('aux',maintenance_request=lambda *a:False),'els_server.storage':module('storage',__path__=[]),'els_server.storage.read_scope':module('reads',committed_reads=lambda **k:contextlib.nullcontext())}
  with patch.dict(sys.modules,deps):namespace['publish'](workers,s.handle,(types.SimpleNamespace(kind=kind),),independent=True)
  self.assertEqual(len(calls),expected)
 def test_unchanged_glass_attack_reuses_exact_scope(self):self.check_case(0xb8,True,0)
 def test_unchanged_statistics_reuses_exact_scope(self):self.check_case(0x9e,True,0)
 def test_changed_statistics_rebuilds(self):self.check_case(0x9e,False,1)
 def test_changed_glass_scope_rebuilds(self):self.check_case(0xb8,False,1)
 def test_glass_transition_still_rebuilds(self):self.check_case(0xbb,True,1)
if __name__=='__main__':unittest.main()
