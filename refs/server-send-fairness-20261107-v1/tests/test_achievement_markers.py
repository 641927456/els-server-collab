"""Source-extracted consumer: no-op markers clear only after a guarded success."""
import ast,contextlib,os,sqlite3,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
H=Path(__file__).resolve().parent
SOURCE=H.parent/'source/els_server/domain/achievement_flow.py'
node=next(n for n in ast.parse(SOURCE.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='synchronize')
class MarkerTests(unittest.TestCase):
 def setUp(self):
  self.plans=[];self.guards=0;self.fail_guard=None;self.fail_plan=False;self.fail_encode=False
  now=2000000000
  self.actor=types.SimpleNamespace(role='game',phase='town_ready',account=types.SimpleNamespace(account_id=1,uid=1001),
   _achievement_play_day=(1,(now+28800)//86400),_achievement_notebook_source=(1,1001,17))
  self.response=[types.SimpleNamespace(event_id=0x201,kind=0x9c)]
  def guard(db):
   self.guards+=1
   if self.guards==self.fail_guard:raise ValueError('owned guard failure')
  def plan(db,account,owner,stamp,**options):
   self.assertTrue(db.in_transaction);self.plans.append(options.get('condition_types'))
   if self.fail_plan:raise ValueError('owned planner failure')
   return dict(updates=[])
  def encode(message):
   if self.fail_encode:raise ValueError('owned encode failure')
  @contextlib.contextmanager
  def snapshot(path):
   with contextlib.closing(sqlite3.connect(':memory:'))as db:yield db
  self.actor.account.store=types.SimpleNamespace(path='unused-for-owned-memory-snapshot')
  scope=types.ModuleType('els_server.storage.read_scope');scope.snapshot_connection=snapshot
  self.patch=patch.dict(sys.modules,{'els_server.storage.read_scope':scope});self.patch.start();self.addCleanup(self.patch.stop)
  ns=dict(time=types.SimpleNamespace(time=lambda:now),capture=lambda actor:guard,pending_updates=plan,
   state=types.SimpleNamespace(snapshot=lambda *args:dict(completed=[],watched=[])),
   wire=types.SimpleNamespace(summary=lambda *args:object()),points=lambda completed:0,encode_event=encode)
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),ns);self.invoke=lambda response=None:ns['synchronize'](self.actor,None,self.response if response is None else response)
 def test_consumed_note_does_not_query_again(self):
  self.assertIs(self.invoke(),self.response);self.assertIsNone(self.actor._achievement_notebook_source)
  self.assertIs(self.invoke(),self.response);self.assertEqual(self.plans,[{66}]);self.assertEqual(self.guards,2)
 def test_note_and_spa_clear_together(self):
  self.actor._achievement_spa_source=(1,1001,964)
  self.invoke();self.assertIsNone(self.actor._achievement_notebook_source);self.assertIsNone(self.actor._achievement_spa_source)
  self.assertEqual(self.plans,[{7,66}])
 def test_foreign_note_is_not_consumed_or_queried(self):
  self.actor._achievement_notebook_source=(2,1001,17)
  self.assertIs(self.invoke(),self.response);self.assertEqual(self.actor._achievement_notebook_source,(2,1001,17));self.assertFalse(self.plans)
 def test_both_actor_guard_failures_preserve_marker(self):
  for step in(1,2):
   self.guards=0;self.fail_guard=step
   with self.assertRaisesRegex(ValueError,'owned guard failure'):self.invoke()
   self.assertEqual(self.actor._achievement_notebook_source,(1,1001,17))
 def test_planner_failure_preserves_marker(self):
  self.fail_plan=True
  with self.assertRaisesRegex(ValueError,'owned planner failure'):self.invoke()
  self.assertEqual(self.actor._achievement_notebook_source,(1,1001,17))
 def test_cold_summary_encoding_failure_preserves_marker(self):
  self.fail_encode=True
  with self.assertRaisesRegex(ValueError,'owned encode failure'):self.invoke([types.SimpleNamespace(event_id=0x201,kind=0x2f)])
  self.assertEqual(self.actor._achievement_notebook_source,(1,1001,17))
if __name__=='__main__':unittest.main()
